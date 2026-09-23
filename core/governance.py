"""Signed governance actions for explicit authority recovery."""
from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from cryptography.hazmat.primitives import serialization
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .authority_state import AuthorityState, DynamicAuthorityService


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class AuthorityReset:
    reset_id: str
    agent_id: str
    capability_id: str
    governor_id: str
    epoch: int
    reason: str
    issued_at: float
    nonce: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "governance_version": 1,
            "action": "AUTHORITY_RESET",
            "reset_id": self.reset_id,
            "agent_id": self.agent_id,
            "capability_id": self.capability_id,
            "governor_id": self.governor_id,
            "epoch": self.epoch,
            "reason": self.reason,
            "issued_at": self.issued_at,
            "nonce": self.nonce,
        }


@dataclass(frozen=True)
class SignedAuthorityReset:
    payload: dict[str, Any]
    signature: str
    algorithm: str = "Ed25519"

    def as_dict(self) -> dict[str, Any]:
        return {
            "payload": self.payload,
            "signature": self.signature,
            "algorithm": self.algorithm,
        }


def governor_id(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()


def sign_authority_reset(
    reset: AuthorityReset,
    private_key: Ed25519PrivateKey,
) -> SignedAuthorityReset:
    payload = reset.as_dict()
    return SignedAuthorityReset(
        payload=payload,
        signature=base64.b64encode(
            private_key.sign(_canonical(payload))
        ).decode("ascii"),
    )


def verify_authority_reset(
    signed: dict[str, Any],
    public_key: Ed25519PublicKey,
) -> tuple[bool, str]:
    try:
        if signed.get("algorithm") != "Ed25519":
            return False, "unsupported signature algorithm"
        payload = signed["payload"]
        if payload.get("governance_version") != 1:
            return False, "unsupported governance version"
        if payload.get("action") != "AUTHORITY_RESET":
            return False, "unsupported governance action"
        for field in (
            "reset_id",
            "agent_id",
            "capability_id",
            "governor_id",
            "reason",
            "nonce",
        ):
            if not isinstance(payload.get(field), str) or not payload[field]:
                return False, f"invalid governance field: {field}"
        if isinstance(payload.get("epoch"), bool) or not isinstance(
            payload.get("epoch"), int
        ) or payload["epoch"] < 1:
            return False, "invalid governance epoch"
        issued_at = payload.get("issued_at")
        if isinstance(issued_at, bool) or not isinstance(issued_at, (int, float)):
            return False, "invalid governance issued_at"
        now = time.time()
        if issued_at > now + 60:
            return False, "governance action is too far in the future"
        if issued_at < now - 30 * 24 * 3600:
            return False, "governance action is too old"
        expected_governor = governor_id(public_key)
        if payload["governor_id"] != expected_governor:
            return False, "governor identity mismatch"
        public_key.verify(
            base64.b64decode(signed["signature"], validate=True),
            _canonical(payload),
        )
        return True, "valid authority reset"
    except (KeyError, TypeError, ValueError, InvalidSignature):
        return False, "invalid or tampered authority reset"


def create_authority_reset(
    *,
    agent_id: str,
    capability_id: str,
    governor_private_key: Ed25519PrivateKey,
    epoch: int,
    reason: str,
    issued_at: float | None = None,
    reset_id: str | None = None,
    nonce: str | None = None,
) -> SignedAuthorityReset:
    if not reason.strip():
        raise ValueError("reset reason is required")
    if epoch < 1:
        raise ValueError("epoch must be >= 1")
    public_key = governor_private_key.public_key()
    reset = AuthorityReset(
        reset_id=reset_id or str(uuid.uuid4()),
        agent_id=agent_id,
        capability_id=capability_id,
        governor_id=governor_id(public_key),
        epoch=epoch,
        reason=reason,
        issued_at=time.time() if issued_at is None else issued_at,
        nonce=nonce or str(uuid.uuid4()),
    )
    return sign_authority_reset(reset, governor_private_key)

class AuthorityGovernanceService:
    """Apply signed governance actions without bypassing static authority."""

    def __init__(self, storage):
        self.storage = storage

    def reset(
        self,
        signed_reset: dict[str, Any],
        governor_public_key: Ed25519PublicKey,
    ) -> dict[str, Any]:
        ok, reason = verify_authority_reset(signed_reset, governor_public_key)
        if not ok:
            raise PermissionError(reason)

        payload = signed_reset["payload"]
        capability = self.storage.capability(payload["capability_id"])
        if capability is None:
            raise LookupError("capability not found")
        if capability.agent_id != payload["agent_id"]:
            raise PermissionError("governance agent does not match capability")
        if not self.storage.capability_is_active(capability.capability_id):
            raise PermissionError("cannot reset revoked or expired capability")
        if capability.identity_id and not self.storage.identity_is_active(
            capability.identity_id
        ):
            raise PermissionError("cannot reset capability with inactive identity")

        latest = self.storage.latest_authority_reset(
            payload["agent_id"],
            payload["capability_id"],
        )
        expected_epoch = 1 if latest is None else latest["payload"]["epoch"] + 1
        if payload["epoch"] != expected_epoch:
            raise PermissionError("invalid authority reset epoch")
        if latest is not None and payload["issued_at"] <= latest["payload"]["issued_at"]:
            raise PermissionError("authority reset timestamp is not newer")

        snapshot = DynamicAuthorityService(self.storage).snapshot(
            payload["agent_id"],
            payload["capability_id"],
        )
        if snapshot.state != AuthorityState.SUSPENDED:
            raise PermissionError("authority reset requires suspended state")
        events = self.storage.authority_events(
            agent_id=payload["agent_id"],
            capability_id=payload["capability_id"],
        )
        latest_critical = max(
            (
                event["occurred_at"]
                for event in events
                if event["event_type"] in DynamicAuthorityService.CRITICAL_EVENTS
            ),
            default=0.0,
        )
        if payload["issued_at"] <= latest_critical:
            raise PermissionError(
                "governance reset must be issued after the latest critical incident"
            )

        self.storage.register_authority_reset(signed_reset)

        refreshed = DynamicAuthorityService(self.storage).snapshot(
            payload["agent_id"],
            payload["capability_id"],
            now=payload["issued_at"],
        )
        return {
            "reset": signed_reset,
            "snapshot": refreshed.as_dict(),
            "snapshot_sha256": refreshed.digest,
        }
