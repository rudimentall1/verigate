"""Signed decision receipts and execution authorizations.

DecisionReceipt proves what Verigate decided. ExecutionAuthorization is the
separate capability that permits an ALLOW decision to reach an executor.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from core.models import ActionIntent, GuardrailDecision, Decision


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def action_digest(action: dict[str, Any]) -> str:
    """Fingerprint the exact normalized action an executor is authorized to run."""
    return hashlib.sha256(_canonical(action)).hexdigest()


def _sign(payload: dict[str, Any], private_key: Ed25519PrivateKey) -> str:
    return base64.b64encode(private_key.sign(_canonical(payload))).decode("ascii")


def _verify(payload: dict[str, Any], signature: str, public_key: Ed25519PublicKey) -> None:
    public_key.verify(base64.b64decode(signature, validate=True), _canonical(payload))


def receipt_payload(intent: ActionIntent, decision: GuardrailDecision, policy_digest: str) -> dict[str, Any]:
    return {"receipt_version": 1, "intent": intent.as_dict(), "decision": decision.as_dict(), "policy_sha256": policy_digest}

@dataclass(frozen=True)
class DecisionReceipt:
    """Portable proof of the decision made for one action intent."""
    payload: dict[str, Any]
    signature: str
    algorithm: str = "Ed25519"

    def as_dict(self) -> dict[str, Any]:
        return {"payload": self.payload, "signature": self.signature, "algorithm": self.algorithm}


def sign_receipt(intent: ActionIntent, decision: GuardrailDecision, policy_digest: str, private_key: Ed25519PrivateKey) -> DecisionReceipt:
    payload = receipt_payload(intent, decision, policy_digest)
    return DecisionReceipt(payload, _sign(payload, private_key))


@dataclass(frozen=True)
class ExecutionAuthorization:
    """Separate, short-lived execution capability derived from an ALLOW."""
    payload: dict[str, Any]
    signature: str
    algorithm: str = "Ed25519"

    def as_dict(self) -> dict[str, Any]:
        return {"payload": self.payload, "signature": self.signature, "algorithm": self.algorithm}


def issue_execution_authorization(
    receipt: DecisionReceipt,
    private_key: Ed25519PrivateKey,
    *,
    nonce: str,
    ttl_seconds: int = 300,
    capability_id: str | None = None,
    capability_version: int | None = None,
) -> ExecutionAuthorization:
    if receipt.payload["decision"]["decision"] != Decision.ALLOW.value:
        raise PermissionError("execution authorization requires ALLOW")
    now = int(time.time())
    payload = {
        "authorization_version": 1,
        "authorization_id": hashlib.sha256((receipt.signature + nonce).encode("utf-8")).hexdigest(),
        "decision_receipt_sha256": hashlib.sha256(_canonical(receipt.payload) + receipt.signature.encode("ascii")).hexdigest(),
        "intent_id": receipt.payload["intent"]["intent_id"],
        "agent_id": receipt.payload["intent"]["agent_id"],
        "policy_sha256": receipt.payload["policy_sha256"],
        "capability_id": capability_id,
        "capability_version": capability_version,
        "action": receipt.payload["intent"],
        "action_sha256": action_digest(receipt.payload["intent"]),
        "nonce": nonce,
        "issued_at": now,
        "expires_at": now + ttl_seconds,
    }
    return ExecutionAuthorization(payload, _sign(payload, private_key))

def verify_receipt(receipt: dict[str, Any], public_key: Ed25519PublicKey) -> tuple[bool, str]:
    try:
        payload = receipt["payload"]
        signature = receipt["signature"]
        if receipt.get("algorithm") != "Ed25519":
            return False, "unsupported signature algorithm"
        intent = payload["intent"]
        decision = payload["decision"]
        policy_digest = payload["policy_sha256"]
        if intent["intent_id"] != decision["intent_id"]:
            return False, "intent and decision IDs do not match"
        if intent["agent_id"] != decision["agent_id"]:
            return False, "intent and decision agents do not match"
        if (not isinstance(policy_digest, str) or len(policy_digest) != 64
                or any(c not in "0123456789abcdef" for c in policy_digest)):
            return False, "invalid policy fingerprint"
        _verify(payload, signature, public_key)
        return True, "valid decision receipt"
    except (KeyError, TypeError, ValueError, InvalidSignature):
        return False, "invalid or tampered decision receipt"


def verify_execution_authorization(auth: dict[str, Any], public_key: Ed25519PublicKey) -> tuple[bool, str]:
    try:
        if auth.get("algorithm") != "Ed25519":
            return False, "unsupported signature algorithm"
        payload = auth["payload"]
        if payload.get("authorization_version") != 1:
            return False, "unsupported execution authorization version"

        # Reject malformed identity/timing/fingerprint fields before any state
        # transition. The execution boundary must fail closed on ambiguous
        # authorization envelopes, not merely rely on the signature.
        for field in ("authorization_id", "decision_receipt_sha256", "policy_sha256", "intent_id", "agent_id", "nonce"):
            value = payload.get(field)
            if not isinstance(value, str) or not value:
                return False, f"invalid execution authorization field: {field}"
        for field in ("authorization_id", "decision_receipt_sha256"):
            value = payload[field]
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                return False, f"invalid execution authorization fingerprint: {field}"
        if len(payload["authorization_id"]) != 64 or any(c not in "0123456789abcdef" for c in payload["authorization_id"]):
            return False, "invalid execution authorization id"

        issued_at = payload.get("issued_at")
        expires_at = payload.get("expires_at")
        if isinstance(issued_at, bool) or not isinstance(issued_at, int):
            return False, "invalid execution authorization issued_at"
        if isinstance(expires_at, bool) or not isinstance(expires_at, int):
            return False, "invalid execution authorization expires_at"
        now = int(time.time())
        if expires_at < now:
            return False, "execution authorization expired"
        if expires_at <= issued_at:
            return False, "invalid execution authorization lifetime"
        if issued_at > now:
            return False, "execution authorization is not active yet"

        action = payload["action"]
        if not isinstance(action, dict):
            return False, "invalid authorized action"
        if action["intent_id"] != payload["intent_id"] or action["agent_id"] != payload["agent_id"]:
            return False, "authorized action identity mismatch"
        action_sha256 = payload["action_sha256"]
        if (not isinstance(action_sha256, str) or len(action_sha256) != 64
                or any(c not in "0123456789abcdef" for c in action_sha256)):
            return False, "invalid action fingerprint"
        if action_digest(action) != action_sha256:
            return False, "authorized action fingerprint mismatch"
        _verify(payload, auth["signature"], public_key)
        return True, "valid execution authorization"
    except (KeyError, TypeError, ValueError, InvalidSignature):
        return False, "invalid or tampered execution authorization"


@dataclass(frozen=True)
class ExecutionReceipt:
    """Proof signed by the execution boundary after an execution attempt."""
    payload: dict[str, Any]
    signature: str
    algorithm: str = "Ed25519"

    def as_dict(self) -> dict[str, Any]:
        return {"payload": self.payload, "signature": self.signature, "algorithm": self.algorithm}


def execution_receipt_payload(
    authorization: dict[str, Any],
    *,
    status: str,
    transaction_ref: str | None,
    executor: str,
    error: str | None = None,
    receipt_id: str | None = None,
    previous_receipt_sha256: str | None = None,
    confirmation_ref: str | None = None,
    confirmation_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    auth_payload = authorization["payload"]
    action = auth_payload["action"]
    if status not in {"SUBMITTED", "CONFIRMED", "FAILED"}:
        raise ValueError("invalid execution receipt status")
    return {
        "execution_receipt_version": 1,
        "receipt_id": receipt_id or str(uuid.uuid4()),
        "authorization_id": auth_payload["authorization_id"],
        "decision_receipt_sha256": auth_payload["decision_receipt_sha256"],
        "intent_id": auth_payload["intent_id"],
        "agent_id": auth_payload["agent_id"],
        "action_sha256": auth_payload["action_sha256"],
        "network": action.get("network"),
        "status": status,
        "transaction_ref": transaction_ref,
        "executor": executor,
        "error": error,
        "previous_receipt_sha256": previous_receipt_sha256,
        "confirmation_ref": confirmation_ref,
        "confirmation_data": confirmation_data,
        "executed_at": int(time.time()),
    }


def sign_execution_receipt(
    authorization: dict[str, Any],
    *,
    status: str,
    transaction_ref: str | None,
    executor: str,
    private_key: Ed25519PrivateKey,
    error: str | None = None,
    receipt_id: str | None = None,
    previous_receipt_sha256: str | None = None,
    confirmation_ref: str | None = None,
    confirmation_data: dict[str, Any] | None = None,
) -> ExecutionReceipt:
    payload = execution_receipt_payload(
        authorization,
        status=status,
        transaction_ref=transaction_ref,
        executor=executor,
        error=error,
        receipt_id=receipt_id,
        previous_receipt_sha256=previous_receipt_sha256,
        confirmation_ref=confirmation_ref,
        confirmation_data=confirmation_data,
    )
    return ExecutionReceipt(payload, _sign(payload, private_key))


def verify_execution_receipt(
    receipt: dict[str, Any],
    public_key: Ed25519PublicKey,
    authorization: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    try:
        if receipt.get("algorithm") != "Ed25519":
            return False, "unsupported signature algorithm"
        payload = receipt["payload"]
        if payload["execution_receipt_version"] != 1:
            return False, "unsupported execution receipt version"
        if payload["status"] not in {"SUBMITTED", "CONFIRMED", "FAILED"}:
            return False, "invalid execution receipt status"
        if not payload["receipt_id"] or not payload["authorization_id"] or not payload["intent_id"]:
            return False, "invalid execution receipt identity"
        if payload["status"] in {"SUBMITTED", "CONFIRMED"} and not payload["transaction_ref"]:
            return False, "execution receipt is missing transaction reference"
        action_sha256 = payload["action_sha256"]
        if not isinstance(action_sha256, str) or len(action_sha256) != 64:
            return False, "invalid execution action fingerprint"
        _verify(payload, receipt["signature"], public_key)
        if authorization is not None:
            auth = authorization["payload"]
            if payload["authorization_id"] != auth["authorization_id"]:
                return False, "execution receipt authorization mismatch"
            if payload["intent_id"] != auth["intent_id"]:
                return False, "execution receipt intent mismatch"
            if payload["action_sha256"] != auth["action_sha256"]:
                return False, "execution receipt action fingerprint mismatch"
        return True, "valid execution receipt"
    except (KeyError, TypeError, ValueError, InvalidSignature):
        return False, "invalid or tampered execution receipt"


# Backward-compatible name for existing consumers.
AuthorizationReceipt = DecisionReceipt
