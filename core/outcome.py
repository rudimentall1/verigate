
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
    observed_effect: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in OUTCOME_STATUSES:
        raise ValueError("invalid outcome status")
    if evidence_kind not in EVIDENCE_KINDS:
        raise ValueError("invalid outcome evidence kind")
    if not executor_id or not evidence_ref:
        raise ValueError("executor_id and evidence_ref are required")
    if len(result_sha256) != 64:
        raise ValueError("result_sha256 must be a SHA-256 hex digest")
    if observed_effect is not None:
        if not isinstance(observed_effect, dict):
            raise ValueError("observed_effect must be a serialized ObservedEffect")
        if observed_effect.get("authorization_id") != execution_receipt["payload"]["authorization_id"]:
            raise ValueError("observed effect authorization mismatch")
        if observed_effect.get("action_sha256") != execution_receipt["payload"]["action_sha256"]:
            raise ValueError("observed effect action fingerprint mismatch")
        if observed_effect.get("evidence_kind") != evidence_kind:
            raise ValueError("observed effect evidence kind mismatch")
        if observed_effect.get("evidence_ref") != evidence_ref:
            raise ValueError("observed effect evidence reference mismatch")
        if observed_effect.get("result_sha256") != result_sha256:
            raise ValueError("observed effect result fingerprint mismatch")
        if len(str(observed_effect.get("observation_sha256", ""))) != 64:
            raise ValueError("observed effect fingerprint is required")
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
        "observed_effect": observed_effect,
        "observed_effect_sha256": digest(observed_effect) if observed_effect is not None else None,
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

    def verify_and_record(
        self,
        attestation: dict[str, Any],
        *,
        record_authority_event: bool = True,
    ) -> dict[str, Any]:
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
            record_authority_event
            and claim["status"] in {"SUCCEEDED", "FAILED"}
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
            "attestation_type": payload["attestor_type"],
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

        attestation_type = "EXECUTOR_SELF_REPORT" if (
            registered_attestor["attestor_type"] == "EXECUTOR"
        ) else registered_attestor["attestor_type"]

        if attestation_type == "CHAIN_VERIFIER":
            # A chain verifier observes the transaction independently after the
            # wallet hand-off. It must not rely on an issuer-signed CONFIRMED
            # status that was derived from caller-supplied confirmation data.
            if receipt_payload["status"] != "SUBMITTED":
                raise ValueError("CHAIN_VERIFIER requires the original SUBMITTED wallet receipt")
        else:
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
        observed_effect = claim.get("observed_effect")
        if observed_effect is not None:
            canonical_fields = {
                key: observed_effect.get(key)
                for key in (
                    "verifier_type", "evidence_kind", "effect_status", "authorization_id",
                    "action_sha256", "observed_at", "evidence_ref", "result_sha256", "observation",
                )
            }
            expected_observation_sha256 = digest(canonical_fields)
            if observed_effect.get("observation_sha256") != expected_observation_sha256:
                raise ValueError("observed effect fingerprint mismatch")
            if claim.get("observed_effect_sha256") != digest(observed_effect):
                raise ValueError("outcome claim observed-effect fingerprint mismatch")
            if observed_effect.get("authorization_id") != claim["authorization_id"]:
                raise ValueError("observed effect authorization mismatch")
            if observed_effect.get("action_sha256") != claim["action_sha256"]:
                raise ValueError("observed effect action mismatch")
            if observed_effect.get("evidence_kind") != claim["evidence_kind"] or observed_effect.get("evidence_ref") != claim["evidence_ref"]:
                raise ValueError("observed effect evidence binding mismatch")
            if observed_effect.get("result_sha256") != claim["result_sha256"]:
                raise ValueError("observed effect result binding mismatch")
        if attestation_type == "EXECUTOR_SELF_REPORT":
            if claim["executor_id"] != registered_attestor["attestor_id"]:
                raise ValueError("executor self-report identity mismatch")
        elif attestation_type == "EXTERNAL_VERIFIER":
            pass
        elif attestation_type == "CHAIN_VERIFIER":
            if claim["evidence_kind"] != "CHAIN_RECEIPT":
                raise ValueError("chain verifier requires CHAIN_RECEIPT evidence")
            if not isinstance(observed_effect, dict):
                raise ValueError("CHAIN_VERIFIER requires a signed ObservedEffect")
            if observed_effect.get("verifier_type") != "CHAIN_VERIFIER_EVM":
                raise ValueError("CHAIN_VERIFIER requires the supported CHAIN_VERIFIER_EVM evidence type")
            if observed_effect.get("effect_status") != claim["status"]:
                raise ValueError("chain observed effect status does not match outcome claim")
            if observed_effect.get("evidence_kind") != "CHAIN_RECEIPT":
                raise ValueError("chain observed effect must use CHAIN_RECEIPT evidence")
            observation = observed_effect.get("observation")
            if not isinstance(observation, dict) or observation.get("network") != "EVM":
                raise ValueError("CHAIN_VERIFIER EVM observation is missing its network binding")

            # Bind the chain observation to the *original signed authorization*,
            # not merely to fields copied into an executor's receipt metadata.
            artifacts = self.storage.authorization_by_id(claim["authorization_id"])
            authorization = artifacts.get("execution_authorization") if artifacts else None
            if not isinstance(authorization, dict):
                raise LookupError("stored signed execution authorization not found")
            auth_valid, auth_reason = verify_execution_receipt(
                receipt, self.issuer_public_key, authorization
            )
            if not auth_valid:
                raise ValueError(f"execution receipt is not bound to stored authorization: {auth_reason}")
            action = authorization["payload"].get("action")
            metadata = action.get("metadata") if isinstance(action, dict) else None
            expected_tx = metadata.get("evm_transaction") if isinstance(metadata, dict) else None
            if (
                not isinstance(action, dict)
                or not isinstance(action.get("network"), str)
                or not action["network"].strip()
            ):
                raise ValueError("CHAIN_VERIFIER authorization must identify an EVM network")
            if not isinstance(expected_tx, dict):
                raise ValueError("CHAIN_VERIFIER authorization has no signed EVM transaction")
            expected_chain_id = expected_tx.get("chain_id")
            expected_to = expected_tx.get("to")
            expected_value = expected_tx.get("value_wei")
            expected_data = expected_tx.get("data")
            if (
                isinstance(expected_chain_id, bool) or not isinstance(expected_chain_id, int)
                or expected_chain_id <= 0
                or not isinstance(expected_to, str) or len(expected_to) != 42
                or not expected_to.startswith("0x")
                or any(char not in "0123456789abcdefABCDEF" for char in expected_to[2:])
                or isinstance(expected_value, bool) or not isinstance(expected_value, int)
                or expected_value < 0
                or not isinstance(expected_data, str) or not expected_data.startswith("0x")
                or len(expected_data[2:]) % 2
                or any(char not in "0123456789abcdefABCDEF" for char in expected_data[2:])
            ):
                raise ValueError("signed EVM transaction envelope is malformed")

            import hashlib
            expected_calldata_sha256 = hashlib.sha256(
                expected_data.lower().encode("utf-8")
            ).hexdigest()
            submission = receipt_payload.get("submission_data")
            if not isinstance(submission, dict):
                raise ValueError("CHAIN_VERIFIER requires signed wallet submission metadata")
            if (
                submission.get("source") != "anna_eip1193_wallet"
                or receipt_payload.get("executor") != "anna-eip1193-wallet"
            ):
                raise ValueError("CHAIN_VERIFIER requires the signed Anna EIP-1193 wallet submission path")
            for field in ("sender", "chain_id", "to", "value_wei", "calldata_sha256"):
                if field not in submission:
                    raise ValueError(f"signed wallet submission metadata is missing {field}")
            sender = submission["sender"]
            if (
                not isinstance(sender, str) or len(sender) != 42
                or not sender.startswith("0x")
                or any(char not in "0123456789abcdefABCDEF" for char in sender[2:])
            ):
                raise ValueError("signed wallet submission sender is malformed")
            if (
                isinstance(submission["chain_id"], bool)
                or not isinstance(submission["chain_id"], int)
                or submission["chain_id"] != expected_chain_id
            ):
                raise ValueError("wallet submission chain ID does not match signed authorization")
            if not isinstance(submission["to"], str) or submission["to"].lower() != expected_to.lower():
                raise ValueError("wallet submission destination does not match signed authorization")
            if (
                isinstance(submission["value_wei"], bool)
                or not isinstance(submission["value_wei"], int)
                or submission["value_wei"] != expected_value
            ):
                raise ValueError("wallet submission value does not match signed authorization")
            if (
                not isinstance(submission["calldata_sha256"], str)
                or submission["calldata_sha256"] != expected_calldata_sha256
            ):
                raise ValueError("wallet submission calldata does not match signed authorization")
            expected_network = str(action.get("network") or "").lower()
            if str(receipt_payload.get("network") or "").lower() != expected_network:
                raise ValueError("execution receipt network does not match signed authorization")

            transaction_hash = receipt_payload.get("transaction_ref")
            if (
                not isinstance(transaction_hash, str) or len(transaction_hash) != 66
                or not transaction_hash.startswith("0x")
                or any(char not in "0123456789abcdefABCDEF" for char in transaction_hash[2:])
            ):
                raise ValueError("SUBMITTED receipt has no valid EVM transaction hash")
            observed_hash = observation.get("transaction_hash")
            if not isinstance(observed_hash, str) or observed_hash.lower() != transaction_hash.lower():
                raise ValueError("chain observation transaction hash does not match SUBMITTED receipt")
            if (
                isinstance(observation.get("chain_id"), bool)
                or not isinstance(observation.get("chain_id"), int)
                or observation["chain_id"] != expected_chain_id
            ):
                raise ValueError("chain observation ID does not match signed authorization")

            # When the RPC has returned the transaction object, bind every
            # observed field even while the receipt is still below finality.
            observed_sender = observation.get("transaction_from")
            observed_to = observation.get("transaction_to")
            observed_value = observation.get("transaction_value_wei")
            observed_calldata = observation.get("transaction_calldata_sha256")
            if observed_sender is not None and (
                not isinstance(observed_sender, str) or observed_sender.lower() != sender.lower()
            ):
                raise ValueError("observed chain sender does not match signed wallet submission")
            if observed_to is not None and (
                not isinstance(observed_to, str) or observed_to.lower() != expected_to.lower()
            ):
                raise ValueError("observed chain destination does not match signed authorization")
            if observed_value is not None and observed_value != str(expected_value):
                raise ValueError("observed chain value does not match signed authorization")
            if observed_calldata is not None and observed_calldata != expected_calldata_sha256:
                raise ValueError("observed chain calldata does not match signed authorization")

            if observed_effect["effect_status"] == "UNKNOWN":
                if observation.get("state") != "PENDING":
                    raise ValueError("UNKNOWN chain outcome requires PENDING chain evidence")
            else:
                expected_state = "CONFIRMED" if observed_effect["effect_status"] == "SUCCEEDED" else "FAILED"
                if observation.get("state") != expected_state:
                    raise ValueError("terminal chain outcome does not match observed chain state")
                confirmations = observation.get("confirmations")
                required_confirmations = observation.get("required_confirmations")
                if (
                    isinstance(confirmations, bool) or not isinstance(confirmations, int)
                    or isinstance(required_confirmations, bool) or not isinstance(required_confirmations, int)
                    or required_confirmations < 1 or confirmations < required_confirmations
                ):
                    raise ValueError("terminal chain outcome has insufficient confirmation evidence")
                canonical_hash = observation.get("canonical_block_hash")
                block_hash = observation.get("block_hash")
                receipt_hash = observation.get("receipt_sha256")
                block_number = observation.get("receipt_block_number")
                if (
                    not isinstance(canonical_hash, str) or len(canonical_hash) != 66
                    or not canonical_hash.startswith("0x")
                    or any(char not in "0123456789abcdefABCDEF" for char in canonical_hash[2:])
                    or not isinstance(block_hash, str) or block_hash.lower() != canonical_hash.lower()
                ):
                    raise ValueError("terminal chain outcome is missing canonical block hash binding")
                if (
                    not isinstance(receipt_hash, str) or len(receipt_hash) != 64
                    or any(char not in "0123456789abcdef" for char in receipt_hash)
                    or isinstance(block_number, bool) or not isinstance(block_number, int)
                    or block_number < 0
                ):
                    raise ValueError("terminal chain outcome is missing canonical receipt evidence")
                if observed_sender is None or observed_to is None or observed_value is None or observed_calldata is None:
                    raise ValueError("terminal chain outcome is missing transaction binding evidence")
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
