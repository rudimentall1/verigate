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


@dataclass(frozen=True)
class GovernanceMember:
    governor_id: str
    role: str
    public_key_b64: str

    @classmethod
    def from_public_key(cls, public_key: Ed25519PublicKey, role: str) -> "GovernanceMember":
        raw = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return cls(
            governor_id=governor_id(public_key),
            role=role,
            public_key_b64=base64.b64encode(raw).decode("ascii"),
        )

    def public_key(self) -> Ed25519PublicKey:
        raw = base64.b64decode(self.public_key_b64, validate=True)
        if len(raw) != 32:
            raise ValueError("invalid governance public key")
        return Ed25519PublicKey.from_public_bytes(raw)

    def as_dict(self) -> dict[str, Any]:
        return {
            "governor_id": self.governor_id,
            "role": self.role,
            "public_key_b64": self.public_key_b64,
        }
@dataclass(frozen=True)
class GovernancePolicy:
    policy_id: str
    version: int
    threshold: int
    members: tuple[GovernanceMember, ...]
    required_roles: tuple[tuple[str, int], ...] = ()
    max_approval_lifetime_seconds: int = 300
    allowed_actions: tuple[str, ...] = ("AUTHORITY_RESET",)

    def role_requirements(self) -> dict[str, int]:
        return dict(self.required_roles)

    def as_dict(self) -> dict[str, Any]:
        return {
            "governance_version": 1,
            "policy_id": self.policy_id,
            "version": self.version,
            "threshold": self.threshold,
            "members": [member.as_dict() for member in self.members],
            "required_roles": dict(self.required_roles),
            "max_approval_lifetime_seconds": self.max_approval_lifetime_seconds,
            "allowed_actions": list(self.allowed_actions),
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.as_dict())).hexdigest()

    def validate(self) -> None:
        if self.version < 1 or self.threshold < 1:
            raise ValueError("invalid governance policy version or threshold")
        if self.threshold > len(self.members):
            raise ValueError("governance threshold exceeds member count")
        if self.max_approval_lifetime_seconds <= 0:
            raise ValueError("approval lifetime must be positive")
        ids = set()
        keys = set()
        for member in self.members:
            if not member.governor_id or not member.role:
                raise ValueError("governance members require id and role")
            if member.governor_id in ids:
                raise ValueError("duplicate governance member")
            ids.add(member.governor_id)
            public_key = member.public_key()
            if governor_id(public_key) != member.governor_id:
                raise ValueError("governance member fingerprint mismatch")
            if member.public_key_b64 in keys:
                raise ValueError("duplicate governance public key")
            keys.add(member.public_key_b64)
        seen_roles = set()
        for role, count in self.required_roles:
            if not role or count < 1:
                raise ValueError("invalid required governance role")
            if role in seen_roles:
                raise ValueError("duplicate required governance role")
            seen_roles.add(role)
            if count > sum(1 for member in self.members if member.role == role):
                raise ValueError("required role exceeds role membership")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GovernancePolicy":
        members = tuple(
            GovernanceMember(
                governor_id=item["governor_id"],
                role=item["role"],
                public_key_b64=item["public_key_b64"],
            )
            for item in data["members"]
        )
        policy = cls(
            policy_id=data["policy_id"],
            version=int(data.get("version", 1)),
            threshold=int(data["threshold"]),
            members=members,
            required_roles=tuple(
                (str(role), int(count))
                for role, count in data.get("required_roles", {}).items()
            ),
            max_approval_lifetime_seconds=int(
                data.get("max_approval_lifetime_seconds", 300)
            ),
            allowed_actions=tuple(data.get("allowed_actions", ("AUTHORITY_RESET",))),
        )
        policy.validate()
        return policy


@dataclass(frozen=True)
class GovernanceAction:
    action_id: str
    action: str
    agent_id: str
    capability_id: str
    epoch: int
    reason: str
    policy_sha256: str
    issued_at: float
    expires_at: float
    nonce: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "governance_version": 1,
            "action": self.action,
            "action_id": self.action_id,
            "agent_id": self.agent_id,
            "capability_id": self.capability_id,
            "epoch": self.epoch,
            "reason": self.reason,
            "policy_sha256": self.policy_sha256,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.as_dict())).hexdigest()
@dataclass(frozen=True)
class GovernanceApproval:
    action_digest: str
    governor_id: str
    role: str
    approval_id: str
    issued_at: float
    expires_at: float
    nonce: str
    signature: str
    algorithm: str = "Ed25519"

    def payload(self) -> dict[str, Any]:
        return {
            "governance_version": 1,
            "action_digest": self.action_digest,
            "governor_id": self.governor_id,
            "role": self.role,
            "approval_id": self.approval_id,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "payload": self.payload(),
            "signature": self.signature,
            "algorithm": self.algorithm,
        }
def create_governance_action(
    *,
    action: str,
    agent_id: str,
    capability_id: str,
    epoch: int,
    reason: str,
    policy: GovernancePolicy,
    issued_at: float | None = None,
    expires_at: float | None = None,
    action_id: str | None = None,
    nonce: str | None = None,
) -> GovernanceAction:
    policy.validate()
    if action not in policy.allowed_actions:
        raise ValueError("governance action is not allowed by policy")
    if epoch < 1 or not reason.strip():
        raise ValueError("invalid governance action")
    issued = time.time() if issued_at is None else issued_at
    expiry = (
        issued + policy.max_approval_lifetime_seconds
        if expires_at is None else expires_at
    )
    if expiry <= issued or expiry - issued > policy.max_approval_lifetime_seconds:
        raise ValueError("invalid governance action expiry")
    return GovernanceAction(
        action_id=action_id or str(uuid.uuid4()),
        action=action,
        agent_id=agent_id,
        capability_id=capability_id,
        epoch=epoch,
        reason=reason,
        policy_sha256=policy.digest,
        issued_at=issued,
        expires_at=expiry,
        nonce=nonce or str(uuid.uuid4()),
    )


def sign_governance_approval(
    action: GovernanceAction,
    *,
    role: str,
    private_key: Ed25519PrivateKey,
    issued_at: float | None = None,
    expires_at: float | None = None,
    approval_id: str | None = None,
    nonce: str | None = None,
) -> GovernanceApproval:
    issued = time.time() if issued_at is None else issued_at
    expiry = (
        min(action.expires_at, issued + 300)
        if expires_at is None else expires_at
    )
    payload = {
        "governance_version": 1,
        "action_digest": action.digest,
        "governor_id": governor_id(private_key.public_key()),
        "role": role,
        "approval_id": approval_id or str(uuid.uuid4()),
        "issued_at": issued,
        "expires_at": expiry,
        "nonce": nonce or str(uuid.uuid4()),
    }
    signature = base64.b64encode(
        private_key.sign(_canonical(payload))
    ).decode("ascii")
    return GovernanceApproval(
        action_digest=payload["action_digest"],
        governor_id=payload["governor_id"],
        role=role,
        approval_id=payload["approval_id"],
        issued_at=issued,
        expires_at=expiry,
        nonce=payload["nonce"],
        signature=signature,
    )
def _member_for_governor(policy: GovernancePolicy, governor: str) -> GovernanceMember | None:
    return next(
        (member for member in policy.members if member.governor_id == governor),
        None,
    )


def verify_governance_approval(
    signed: dict[str, Any],
    policy: GovernancePolicy,
    *,
    now: float | None = None,
) -> tuple[bool, str]:
    try:
        policy.validate()
        if signed.get("algorithm") != "Ed25519":
            return False, "unsupported governance approval algorithm"
        payload = signed["payload"]
        required = (
            "action_digest", "governor_id", "role", "approval_id", "nonce",
        )
        if payload.get("governance_version") != 1:
            return False, "unsupported governance approval version"
        if any(not isinstance(payload.get(field), str) or not payload[field] for field in required):
            return False, "invalid governance approval fields"
        if not isinstance(payload.get("issued_at"), (int, float)) or isinstance(payload.get("issued_at"), bool):
            return False, "invalid governance approval issued_at"
        if not isinstance(payload.get("expires_at"), (int, float)) or isinstance(payload.get("expires_at"), bool):
            return False, "invalid governance approval expires_at"
        now = time.time() if now is None else now
        if payload["issued_at"] > now + 60:
            return False, "governance approval is too far in the future"
        if payload["expires_at"] <= now:
            return False, "governance approval has expired"
        if payload["expires_at"] <= payload["issued_at"]:
            return False, "governance approval expiry is invalid"
        if payload["expires_at"] - payload["issued_at"] > policy.max_approval_lifetime_seconds:
            return False, "governance approval lifetime exceeds policy"
        member = _member_for_governor(policy, payload["governor_id"])
        if member is None or member.role != payload["role"]:
            return False, "governance signer is not authorized for this role"
        member.public_key().verify(
            base64.b64decode(signed["signature"], validate=True),
            _canonical(payload),
        )
        return True, "valid governance approval"
    except (KeyError, TypeError, ValueError, InvalidSignature):
        return False, "invalid or tampered governance approval"
def verify_governance_quorum(
    action: GovernanceAction | dict[str, Any],
    approvals: list[dict[str, Any]],
    policy: GovernancePolicy,
    *,
    now: float | None = None,
) -> tuple[bool, str]:
    policy.validate()
    payload = action.as_dict() if isinstance(action, GovernanceAction) else action
    now = time.time() if now is None else now
    if payload.get("governance_version") != 1:
        return False, "unsupported governance action version"
    string_fields = (
        "action",
        "action_id",
        "agent_id",
        "capability_id",
        "reason",
        "policy_sha256",
        "nonce",
    )
    if any(not isinstance(payload.get(field), str) or not payload[field] for field in string_fields):
        return False, "invalid governance action fields"
    if isinstance(payload.get("epoch"), bool) or not isinstance(payload.get("epoch"), int) or payload["epoch"] < 1:
        return False, "invalid governance action epoch"
    for field in ("issued_at", "expires_at"):
        if isinstance(payload.get(field), bool) or not isinstance(payload.get(field), (int, float)):
            return False, f"invalid governance action {field}"
    if payload.get("policy_sha256") != policy.digest:
        return False, "governance policy fingerprint mismatch"
    if payload.get("action") not in policy.allowed_actions:
        return False, "governance action is not allowed"
    if payload["issued_at"] > now + 60:
        return False, "governance action is too far in the future"
    if payload["expires_at"] <= now:
        return False, "governance action has expired"
    if payload["expires_at"] <= payload["issued_at"]:
        return False, "governance action expiry is invalid"
    if payload["expires_at"] - payload["issued_at"] > policy.max_approval_lifetime_seconds:
        return False, "governance action lifetime exceeds policy"
    seen_governors: set[str] = set()
    seen_nonces: set[str] = set()
    role_counts: dict[str, int] = {}
    valid = 0
    action_digest = (
        action.digest if isinstance(action, GovernanceAction)
        else hashlib.sha256(_canonical(payload)).hexdigest()
    )
    for signed in approvals:
        ok, reason = verify_governance_approval(signed, policy, now=now)
        if not ok:
            return False, reason
        approval = signed["payload"]
        if approval["action_digest"] != action_digest:
            return False, "governance approval targets a different action"
        if approval["governor_id"] in seen_governors:
            return False, "duplicate governance signer"
        if approval["nonce"] in seen_nonces:
            return False, "duplicate governance approval nonce"
        seen_governors.add(approval["governor_id"])
        seen_nonces.add(approval["nonce"])
        role_counts[approval["role"]] = role_counts.get(approval["role"], 0) + 1
        valid += 1
    if valid < policy.threshold:
        return False, "governance threshold not reached"
    for role, minimum in policy.required_roles:
        if role_counts.get(role, 0) < minimum:
            return False, f"required governance role missing: {role}"
    return True, "governance quorum satisfied"
def _multiparty_envelope(
    action: GovernanceAction,
    approvals: list[dict[str, Any]],
    policy: GovernancePolicy,
) -> dict[str, Any]:
    return {
        "payload": action.as_dict(),
        "approvals": approvals,
        "policy": policy.as_dict(),
        "governance_policy_sha256": policy.digest,
        "algorithm": "Ed25519-MULTIPARTY",
    }


def _validate_reset_common(
    storage,
    payload: dict[str, Any],
) -> tuple[Any, list[dict[str, Any]]]:
    capability = storage.capability(payload["capability_id"])
    if capability is None:
        raise LookupError("capability not found")
    if capability.agent_id != payload["agent_id"]:
        raise PermissionError("governance agent does not match capability")
    if not storage.capability_is_active(capability.capability_id):
        raise PermissionError("cannot reset revoked or expired capability")
    if capability.identity_id and not storage.identity_is_active(capability.identity_id):
        raise PermissionError("cannot reset capability with inactive identity")
    latest = storage.latest_authority_reset(
        payload["agent_id"],
        payload["capability_id"],
    )
    expected_epoch = 1 if latest is None else latest["payload"]["epoch"] + 1
    if payload["epoch"] != expected_epoch:
        raise PermissionError("invalid authority reset epoch")
    if latest is not None and payload["issued_at"] <= latest["payload"]["issued_at"]:
        raise PermissionError("authority reset timestamp is not newer")
    snapshot = DynamicAuthorityService(storage).snapshot(
        payload["agent_id"],
        payload["capability_id"],
    )
    if snapshot.state != AuthorityState.SUSPENDED:
        raise PermissionError("authority reset requires suspended state")
    events = storage.authority_events(
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
    return snapshot, events


def multiparty_governance_reset(
    storage,
    action: GovernanceAction | dict[str, Any],
    approvals: list[dict[str, Any]],
    policy: GovernancePolicy,
) -> dict[str, Any]:
    """Apply a quorum-approved authority reset without a single governor key."""
    now = time.time()
    ok, reason = verify_governance_quorum(action, approvals, policy, now=now)
    if not ok:
        raise PermissionError(reason)
    payload = action.as_dict() if isinstance(action, GovernanceAction) else action
    if payload.get("action") != "AUTHORITY_RESET":
        raise PermissionError("unsupported multi-party governance action")
    if payload.get("policy_sha256") != policy.digest:
        raise PermissionError("governance policy fingerprint mismatch")
    if payload.get("issued_at", 0) > now + 60:
        raise PermissionError("governance action is too far in the future")
    _, _ = _validate_reset_common(storage, payload)
    envelope = _multiparty_envelope(
        GovernanceAction(**{
            key: payload[key]
            for key in (
                "action_id", "action", "agent_id", "capability_id", "epoch",
                "reason", "policy_sha256", "issued_at", "expires_at", "nonce",
            )
        }),
        approvals,
        policy,
    )
    storage.register_authority_reset(
        envelope,
        governance_approvals=approvals,
    )
    refreshed = DynamicAuthorityService(storage).snapshot(
        payload["agent_id"],
        payload["capability_id"],
        now=payload["issued_at"],
    )
    return {
        "reset": envelope,
        "snapshot": refreshed.as_dict(),
        "snapshot_sha256": refreshed.digest,
        "governance_policy_sha256": policy.digest,
    }


class MultiPartyAuthorityGovernanceService(AuthorityGovernanceService):
    """Quorum-based governance facade for sensitive authority recovery."""

    def reset(
        self,
        action: GovernanceAction | dict[str, Any],
        approvals: list[dict[str, Any]],
        policy: GovernancePolicy,
    ) -> dict[str, Any]:
        return multiparty_governance_reset(
            self.storage,
            action,
            approvals,
            policy,
        )
