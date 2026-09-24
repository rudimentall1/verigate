
import base64
import hashlib
import json
import time
import uuid
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from attest.receipt import verify_execution_receipt
from core.authority_state import DynamicAuthorityService
from core.storage import Storage


OUTCOME_STATUSES = frozenset({"SUCCEEDED", "FAILED", "UNKNOWN"})
ATTESTATION_TYPES = frozenset({
    "EXECUTOR_SELF_REPORT",
    "EXTERNAL_VERIFIER",
    "CHAIN_VERIFIER",
})
ATTESTOR_TYPES = frozenset({"EXECUTOR", "EXTERNAL_VERIFIER", "CHAIN_VERIFIER"})
EVIDENCE_KINDS = frozenset({
    "MCP_RESULT",
    "HTTP_RESPONSE",
    "CHAIN_RECEIPT",
    "EXECUTOR_RESULT",
    "EXTERNAL_REFERENCE",
})


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def key_fingerprint(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()


def sign_payload(payload: dict[str, Any], private_key: Ed25519PrivateKey) -> str:
    return base64.b64encode(private_key.sign(_canonical(payload))).decode("ascii")


def verify_payload_signature(
    payload: dict[str, Any],
    signature: str,
    public_key: Ed25519PublicKey,
) -> tuple[bool, str]:
    try:
        public_key.verify(base64.b64decode(signature), _canonical(payload))
        return True, "valid signature"
    except (InvalidSignature, ValueError, TypeError):
        return False, "invalid outcome attestation signature"


def build_outcome_claim(
    execution_receipt: dict[str, Any],
    *,
    status: str,
    executor_id: str,
    evidence_kind: str,
    evidence_ref: str,
    result_sha256: str,
    observed_at: float | None = None,
    metadata: dict[str, Any] | None = None,
    claim_id: str | None = None,
) -> dict[str, Any]:
    if status not in OUTCOME_STATUSES:
        raise ValueError("invalid outcome status")
    if evidence_kind not in EVIDENCE_KINDS:
        raise ValueError("invalid outcome evidence kind")
    if not executor_id or not evidence_ref:
        raise ValueError("executor_id and evidence_ref are required")
    if len(result_sha256) != 64:
        raise ValueError("result_sha256 must be a SHA-256 hex digest")
    return {
        "outcome_claim_version": 1,
        "claim_id": claim_id or str(uuid.uuid4()),
        "authorization_id": execution_receipt["payload"]["authorization_id"],
        "execution_receipt_sha256": digest(execution_receipt),
        "action_sha256": execution_receipt["payload"]["action_sha256"],
        "intent_id": execution_receipt["payload"]["intent_id"],
        "agent_id": execution_receipt["payload"]["agent_id"],
        "executor_id": executor_id,
        "status": status,
        "evidence_kind": evidence_kind,
        "evidence_ref": evidence_ref,
        "result_sha256": result_sha256,
        "observed_at": time.time() if observed_at is None else observed_at,
        "metadata": metadata or {},
    }


def build_outcome_attestation(
    claim: dict[str, Any],
    *,
    attestor_id: str,
    attestor_type: str,
    private_key: Ed25519PrivateKey,
    attested_at: float | None = None,
) -> dict[str, Any]:
    if attestor_type not in ATTESTATION_TYPES:
        raise ValueError("invalid outcome attestation type")
    payload = {
        "outcome_attestation_version": 1,
        "attestation_id": str(uuid.uuid4()),
        "claim": claim,
        "claim_sha256": digest(claim),
        "attestor_id": attestor_id,
        "attestor_type": attestor_type,
        "attested_at": time.time() if attested_at is None else attested_at,
    }
    return {
        "payload": payload,
        "signature": sign_payload(payload, private_key),
        "algorithm": "Ed25519",
    }


class OutcomeAttestationService:
    """Verify and persist independently signed execution outcomes."""

    def __init__(self, storage: Storage, issuer_public_key: Ed25519PublicKey):
        self.storage = storage
        self.issuer_public_key = issuer_public_key

    def register_attestor(
        self,
        *,
        attestor_id: str,
        public_key_b64: str,
        attestor_type: str,
    ) -> dict[str, Any]:
        if attestor_type not in ATTESTOR_TYPES:
            raise ValueError("invalid attestor type")
        try:
            raw = base64.b64decode(public_key_b64)
            public_key = Ed25519PublicKey.from_public_bytes(raw)
        except (ValueError, TypeError):
            raise ValueError("invalid attestor public key") from None
        item = {
            "attestor_id": attestor_id,
            "key_id": key_fingerprint(public_key),
            "public_key_b64": public_key_b64,
            "attestor_type": attestor_type,
            "status": "ACTIVE",
        }
        self.storage.register_outcome_attestor(item)
        return item

    def verify_and_record(self, attestation: dict[str, Any]) -> dict[str, Any]:
        payload = attestation["payload"]
        claim = payload["claim"]
        attestor_id = payload["attestor_id"]
        registered = self.storage.outcome_attestor(attestor_id)
        if registered is None or registered["status"] != "ACTIVE":
            raise PermissionError("outcome attestor is not registered and active")
        if registered.get("expires_at") is not None and registered["expires_at"] <= time.time():
            raise PermissionError("outcome attestor authority has expired")
        if payload.get("outcome_attestation_version") != 1:
            raise ValueError("unsupported outcome attestation version")
        if payload.get("claim_sha256") != digest(claim):
            raise ValueError("outcome claim fingerprint mismatch")
        if payload.get("attestor_type") not in ATTESTATION_TYPES:
            raise ValueError("invalid outcome attestation type")
        registered_type = registered["attestor_type"]
        expected_type = (
            "EXECUTOR_SELF_REPORT"
            if registered_type == "EXECUTOR"
            else registered_type
        )
        if payload.get("attestor_type") != expected_type:
            raise PermissionError("attestation type does not match registered attestor")
        try:
            public_key = Ed25519PublicKey.from_public_bytes(
                base64.b64decode(registered["public_key_b64"])
            )
        except (ValueError, TypeError):
            raise ValueError("registered attestor key is invalid") from None
        valid, reason = verify_payload_signature(
            payload,
            attestation["signature"],
            public_key,
        )
        if not valid:
            raise PermissionError(reason)

        claim_ok = self._verify_claim(claim, registered)
        claim_id = claim["claim_id"]
        self.storage.record_outcome_claim(claim)
        self.storage.record_outcome_attestation(attestation)

        authority_event = None
        if (
            claim["status"] in {"SUCCEEDED", "FAILED"}
            and payload["attestor_type"] != "EXECUTOR_SELF_REPORT"
        ):
            receipt = self.storage.execution_receipt_by_authorization(
                claim["authorization_id"]
            )
            capability_id = receipt["payload"].get("capability_id") if receipt else None
            if capability_id:
                authority_event = DynamicAuthorityService(self.storage).record_event(
                    agent_id=claim["agent_id"],
                    capability_id=capability_id,
                    identity_id=receipt["payload"].get("identity_id"),
                    event_type=(
                        "EXECUTION_CONFIRMED"
                        if claim["status"] == "SUCCEEDED"
                        else "EXECUTION_FAILED"
                    ),
                    evidence_ref=claim_id,
                    metadata={
                        "outcome_attestation_id": payload["attestation_id"],
                        "attestation_type": payload["attestor_type"],
                    },
                )
        return {
            "valid": True,
            "reason": "valid independent outcome attestation",
            "claim": claim,
            "claim_sha256": digest(claim),
            "attestation_id": payload["attestation_id"],
            "attestation_sha256": digest(attestation),
            "authority_event": authority_event,
            "claim_verification": claim_ok,
        }

    def verify_existing(
        self,
        attestation: dict[str, Any],
    ) -> dict[str, Any]:
        payload = attestation["payload"]
        claim = payload["claim"]
        registered = self.storage.outcome_attestor(payload["attestor_id"])
        if registered is None or registered["status"] != "ACTIVE":
            raise PermissionError("outcome attestor is not registered and active")
        if payload.get("outcome_attestation_version") != 1:
            raise ValueError("unsupported outcome attestation version")
        if payload.get("claim_sha256") != digest(claim):
            raise ValueError("outcome claim fingerprint mismatch")
        expected_type = (
            "EXECUTOR_SELF_REPORT"
            if registered["attestor_type"] == "EXECUTOR"
            else registered["attestor_type"]
        )
        if payload.get("attestor_type") != expected_type:
            raise PermissionError("attestation type does not match registered attestor")
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(registered["public_key_b64"])
        )
        valid, reason = verify_payload_signature(
            payload,
            attestation["signature"],
            public_key,
        )
        if not valid:
            raise PermissionError(reason)
        claim_ok = self._verify_claim(claim, registered)
        return {
            "valid": True,
            "reason": "valid stored outcome attestation",
            "claim_sha256": digest(claim),
            "attestation_sha256": digest(attestation),
            "claim_verification": claim_ok,
        }

    def _verify_claim(
        self,
        claim: dict[str, Any],
        registered_attestor: dict[str, Any],
    ) -> dict[str, Any]:
        if claim.get("outcome_claim_version") != 1:
            raise ValueError("unsupported outcome claim version")
        if claim.get("status") not in OUTCOME_STATUSES:
            raise ValueError("invalid outcome claim status")
        receipt = self.storage.execution_receipt_by_authorization(
            claim["authorization_id"]
        )
        if receipt is None:
            raise LookupError("execution receipt not found")
        valid, reason = verify_execution_receipt(
            receipt,
            self.issuer_public_key,
        )
        if not valid:
            raise ValueError(f"stored execution receipt is invalid: {reason}")
        if claim["execution_receipt_sha256"] != digest(receipt):
            raise ValueError("execution receipt fingerprint mismatch")
        receipt_payload = receipt["payload"]
        if claim["intent_id"] != receipt_payload["intent_id"]:
            raise ValueError("outcome intent mismatch")
        if claim["agent_id"] != receipt_payload["agent_id"]:
            raise ValueError("outcome agent mismatch")
        if claim["action_sha256"] != receipt_payload["action_sha256"]:
            raise ValueError("outcome action fingerprint mismatch")
        if claim["status"] == "SUCCEEDED" and receipt_payload["status"] != "CONFIRMED":
            raise ValueError("successful outcome requires a CONFIRMED execution receipt")
        if claim["status"] == "FAILED" and receipt_payload["status"] != "FAILED":
            raise ValueError("failed outcome requires a FAILED execution receipt")
        if claim["status"] == "UNKNOWN" and receipt_payload["status"] not in {
            "SUBMITTED",
            "CONFIRMED",
            "FAILED",
        }:
            raise ValueError("unknown outcome has invalid execution receipt state")

        attestation_type = "EXECUTOR_SELF_REPORT" if (
            registered_attestor["attestor_type"] == "EXECUTOR"
        ) else registered_attestor["attestor_type"]
        if attestation_type == "EXECUTOR_SELF_REPORT":
            if claim["executor_id"] != registered_attestor["attestor_id"]:
                raise ValueError("executor self-report identity mismatch")
        elif attestation_type == "EXTERNAL_VERIFIER":
            pass
        elif attestation_type == "CHAIN_VERIFIER":
            if claim["evidence_kind"] != "CHAIN_RECEIPT":
                raise ValueError("chain verifier requires CHAIN_RECEIPT evidence")
        else:
            raise PermissionError("attestor type is inconsistent")
        return {
            "valid": True,
            "reason": "claim is bound to a stored signed execution receipt",
            "execution_receipt_sha256": digest(receipt),
        }
    def attestor_status(self, attestor_id: str) -> str | None:
        item = self.storage.outcome_attestor(attestor_id)
        return item["status"] if item else None

    def explain_authorization(self, authorization_id: str) -> dict[str, Any]:
        claims = self.storage.outcome_claims_by_authorization(authorization_id)
        return {
            "authorization_id": authorization_id,
            "claims": claims,
            "attestations": [
                att
                for claim in claims
                for att in self.storage.outcome_attestations_by_claim(
                    claim["claim_id"]
                )
            ],
        }
