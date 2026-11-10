"""Cryptographic identity registry and agent-signed intent verification."""
from __future__ import annotations

import base64
import hashlib
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .models import ActionIntent, AgentIdentity
from .storage import Storage


def _canonical(payload: dict) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def sign_action_intent(
    action: ActionIntent,
    identity_id: str,
    private_key: Ed25519PrivateKey,
) -> str:
    payload = {
        "identity_id": identity_id,
        "action": action.as_dict(),
    }
    return base64.b64encode(private_key.sign(_canonical(payload))).decode("ascii")


def verify_action_signature(
    action: ActionIntent,
    identity_id: str,
    signature: str,
    identity: AgentIdentity,
) -> tuple[bool, str]:
    try:
        if identity.agent_id != action.agent_id:
            return False, "identity agent mismatch"
        if not identity.public_key_b64:
            return False, "identity has no public key"
        raw = base64.b64decode(identity.public_key_b64, validate=True)
        if len(raw) != 32:
            return False, "invalid identity public key"
        public_key = Ed25519PublicKey.from_public_bytes(raw)
        payload = {
            "identity_id": identity_id,
            "action": action.as_dict(),
        }
        public_key.verify(
            base64.b64decode(signature, validate=True),
            _canonical(payload),
        )
        return True, "valid agent action signature"
    except (ValueError, InvalidSignature):
        return False, "invalid or tampered agent action signature"


class IdentityRegistry:
    """Source of truth for active cryptographic agent identities."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def register(self, identity: AgentIdentity) -> AgentIdentity:
        try:
            raw = base64.b64decode(identity.public_key_b64, validate=True)
        except ValueError as exc:
            raise ValueError("invalid identity public key encoding") from exc
        if len(raw) != 32:
            raise ValueError("invalid identity public key length")
        expected_key_id = hashlib.sha256(raw).hexdigest()
        if identity.key_id != expected_key_id:
            raise ValueError("identity key_id does not match public key fingerprint")
        self.storage.register_identity(identity)
        return identity
    def resolve(self, identity_id: str, *, require_active: bool = True) -> AgentIdentity:
        identity = self.storage.identity(identity_id)
        if identity is None:
            raise LookupError("identity not found")
        if require_active and not self.storage.identity_is_active(identity_id):
            raise PermissionError("identity is not active")
        return identity

    def revoke(self, identity_id: str) -> bool:
        return self.storage.revoke_identity(identity_id)

    def active(self, identity_id: str) -> bool:
        return self.storage.identity_is_active(identity_id)

    def authorize_action(
        self,
        identity_id: str,
        action: ActionIntent,
        agent_signature: str,
    ) -> AgentIdentity:
        identity = self.resolve(identity_id)
        valid, reason = verify_action_signature(
            action, identity_id, agent_signature, identity
        )
        if not valid:
            raise PermissionError(reason)
        return identity
