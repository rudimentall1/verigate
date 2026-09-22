"""Signed decision receipts and execution authorizations.

DecisionReceipt proves what Verigate decided. ExecutionAuthorization is the
separate capability that permits an ALLOW decision to reach an executor.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from core.models import ActionIntent, GuardrailDecision, Decision


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


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


def issue_execution_authorization(receipt: DecisionReceipt, private_key: Ed25519PrivateKey, *, nonce: str, ttl_seconds: int = 300) -> ExecutionAuthorization:
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
        if int(payload["expires_at"]) < int(time.time()):
            return False, "execution authorization expired"
        if not payload["nonce"] or not payload["intent_id"] or not payload["agent_id"]:
            return False, "invalid execution authorization fields"
        _verify(payload, auth["signature"], public_key)
        return True, "valid execution authorization"
    except (KeyError, TypeError, ValueError, InvalidSignature):
        return False, "invalid or tampered execution authorization"


# Backward-compatible name for existing consumers.
AuthorizationReceipt = DecisionReceipt
