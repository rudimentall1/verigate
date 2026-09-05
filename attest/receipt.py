"""Cryptographically signed authorization receipts.

A receipt binds the agent action, policy fingerprint, decision and issuer
signature into a portable proof that can be verified offline.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from core.models import ActionIntent, GuardrailDecision


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def receipt_payload(intent: ActionIntent, decision: GuardrailDecision, policy_digest: str) -> dict[str, Any]:
    return {
        "receipt_version": 1,
        "intent": intent.as_dict(),
        "decision": decision.as_dict(),
        "policy_sha256": policy_digest,
    }


@dataclass(frozen=True)
class AuthorizationReceipt:
    payload: dict[str, Any]
    signature: str
    algorithm: str = "Ed25519"

    def as_dict(self) -> dict[str, Any]:
        return {"payload": self.payload, "signature": self.signature, "algorithm": self.algorithm}


def sign_receipt(
    intent: ActionIntent,
    decision: GuardrailDecision,
    policy_digest: str,
    private_key: Ed25519PrivateKey,
) -> AuthorizationReceipt:
    payload = receipt_payload(intent, decision, policy_digest)
    signature = private_key.sign(_canonical(payload))
    return AuthorizationReceipt(
        payload=payload,
        signature=base64.b64encode(signature).decode("ascii"),
    )


def verify_receipt(receipt: dict[str, Any], public_key: Ed25519PublicKey) -> tuple[bool, str]:
    try:
        payload = receipt["payload"]
        signature = base64.b64decode(receipt["signature"], validate=True)
        if receipt.get("algorithm") != "Ed25519":
            return False, "unsupported signature algorithm"
        _ = payload["intent"]["intent_id"]
        _ = payload["decision"]["decision"]
        _ = payload["policy_sha256"]
        public_key.verify(signature, _canonical(payload))
        return True, "valid authorization receipt"
    except (KeyError, TypeError, ValueError, InvalidSignature):
        return False, "invalid or tampered authorization receipt"
