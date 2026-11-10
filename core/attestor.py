"""Governance-controlled attestor authority for Verigate."""

from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.governance import GovernancePolicy, verify_governance_quorum
from core.outcome import ATTESTOR_TYPES, key_fingerprint
from core.storage import Storage

ATTESTOR_ACTIONS = frozenset({
    "ATTESTOR_REGISTER",
    "ATTESTOR_ACTIVATE",
    "ATTESTOR_ROTATE",
    "ATTESTOR_REVOKE",
    "ATTESTOR_EXPIRE",
})


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


class AttestorAuthorityService:
    """Manage outcome attestors only through governance-approved actions."""

    def __init__(self, storage: Storage):
        self.storage = storage

    @staticmethod
    def build_action(
        *,
        action: str,
        attestor_id: str,
        reason: str,
        governance_policy_sha256: str,
        public_key_b64: str | None = None,
        attestor_type: str | None = None,
        expires_at: float | None = None,
        action_id: str | None = None,
        nonce: str | None = None,
        issued_at: float | None = None,
    ) -> dict[str, Any]:
        if action not in ATTESTOR_ACTIONS:
            raise ValueError("invalid attestor governance action")
        if not attestor_id or not reason.strip():
            raise ValueError("attestor_id and reason are required")
        if action in {"ATTESTOR_REGISTER", "ATTESTOR_ROTATE"}:
            if not public_key_b64 or not attestor_type:
                raise ValueError("key and type are required for register/rotate")
            if attestor_type not in ATTESTOR_TYPES:
                raise ValueError("invalid attestor type")
            try:
                raw = base64.b64decode(public_key_b64, validate=True)
                key_fingerprint(Ed25519PublicKey.from_public_bytes(raw))
            except (ValueError, TypeError):
                raise ValueError("invalid attestor public key") from None
        issued = time.time() if issued_at is None else issued_at
        expiry = issued + 300 if expires_at is None else expires_at
        if expiry <= issued:
            raise ValueError("attestor governance action expiry is invalid")
        return {
            "governance_version": 1,
            "action_id": action_id or str(uuid.uuid4()),
            "action": action,
            "attestor_id": attestor_id,
            "reason": reason,
            "governance_policy_sha256": governance_policy_sha256,
            "issued_at": issued,
            "expires_at": expiry,
            "nonce": nonce or str(uuid.uuid4()),
            "public_key_b64": public_key_b64,
            "attestor_type": attestor_type,
            "attestor_expires_at": expires_at,
        }

    def apply(
        self,
        action: dict[str, Any],
        approvals: list[dict[str, Any]],
        policy: GovernancePolicy,
    ) -> dict[str, Any]:
        if action.get("action") not in ATTESTOR_ACTIONS:
            raise PermissionError("unsupported attestor governance action")
        ok, reason = verify_governance_quorum(action, approvals, policy)
        if not ok:
            raise PermissionError(reason)
        if action.get("governance_policy_sha256") != policy.digest:
            raise PermissionError("governance policy fingerprint mismatch")

        attestor_id = action["attestor_id"]
        existing = self.storage.outcome_attestor(attestor_id)
        operation = action["action"]

        if operation == "ATTESTOR_REGISTER":
            if existing is not None:
                raise ValueError("attestor already exists")
            self._validate_key(action)
            self.storage.register_outcome_attestor({
                "attestor_id": attestor_id,
                "key_id": key_fingerprint(
                    Ed25519PublicKey.from_public_bytes(
                        base64.b64decode(action["public_key_b64"], validate=True)
                    )
                ),
                "public_key_b64": action["public_key_b64"],
                "attestor_type": action["attestor_type"],
                "status": "ACTIVE",
                "expires_at": action.get("attestor_expires_at"),
            })
        elif operation == "ATTESTOR_ACTIVATE":
            if existing is None:
                raise LookupError("attestor not found")
            self.storage.set_outcome_attestor_status(attestor_id, "ACTIVE")
        elif operation == "ATTESTOR_ROTATE":
            if existing is None:
                raise LookupError("attestor not found")
            self._validate_key(action)
            self.storage.rotate_outcome_attestor(
                attestor_id,
                key_id=key_fingerprint(
                    Ed25519PublicKey.from_public_bytes(
                        base64.b64decode(action["public_key_b64"], validate=True)
                    )
                ),
                public_key_b64=action["public_key_b64"],
                attestor_type=action["attestor_type"],
                expires_at=action.get("attestor_expires_at"),
            )
        elif operation == "ATTESTOR_REVOKE":
            if existing is None:
                raise LookupError("attestor not found")
            self.storage.revoke_outcome_attestor(attestor_id)
        elif operation == "ATTESTOR_EXPIRE":
            if existing is None:
                raise LookupError("attestor not found")
            self.storage.set_outcome_attestor_status(attestor_id, "EXPIRED")

        envelope = {
            "action": action,
            "approvals": approvals,
            "governance_policy": policy.as_dict(),
            "governance_policy_sha256": policy.digest,
            "action_sha256": digest(action),
            "algorithm": "Ed25519-MULTIPARTY",
            "recorded_at": time.time(),
        }
        self.storage.record_attestor_governance_action(envelope)
        return {
            "status": "APPLIED",
            "attestor": self.storage.outcome_attestor(attestor_id),
            "governance_action": envelope,
        }

    @staticmethod
    def _validate_key(action: dict[str, Any]) -> None:
        try:
            raw = base64.b64decode(action["public_key_b64"], validate=True)
            Ed25519PublicKey.from_public_bytes(raw)
        except (KeyError, ValueError, TypeError):
            raise ValueError("invalid attestor public key") from None
