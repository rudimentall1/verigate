"""Cryptographically signed policy versions for Verigate authority decisions."""
from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .policy import Policy


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class PolicyVersion:
    policy_id: str
    version: int
    policy_sha256: str
    source_ref: str
    parent_sha256: str | None = None
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_version": 1,
            "policy_id": self.policy_id,
            "version": self.version,
            "policy_sha256": self.policy_sha256,
            "source_ref": self.source_ref,
            "parent_sha256": self.parent_sha256,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.as_dict())).hexdigest()


@dataclass(frozen=True)
class SignedPolicyVersion:
    payload: dict[str, Any]
    signature: str
    algorithm: str = "Ed25519"

    def as_dict(self) -> dict[str, Any]:
        return {
            "payload": self.payload,
            "signature": self.signature,
            "algorithm": self.algorithm,
        }


def policy_id(source_ref: str) -> str:
    return hashlib.sha256(
        f"verigate-policy:{source_ref}".encode("utf-8")
    ).hexdigest()


def build_policy_version(
    policy: Policy,
    *,
    source_ref: str,
    version: int = 1,
    parent_sha256: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> PolicyVersion:
    if version < 1:
        raise ValueError("policy version must be >= 1")
    return PolicyVersion(
        policy_id=policy_id(source_ref),
        version=version,
        policy_sha256=policy.digest,
        source_ref=source_ref,
        parent_sha256=parent_sha256,
        metadata=metadata or {},
    )


def sign_policy_version(
    version: PolicyVersion,
    private_key: Ed25519PrivateKey,
) -> SignedPolicyVersion:
    payload = version.as_dict()
    signature = base64.b64encode(private_key.sign(_canonical(payload))).decode("ascii")
    return SignedPolicyVersion(payload, signature)


def verify_policy_version(
    signed: dict[str, Any],
    public_key: Ed25519PublicKey,
) -> tuple[bool, str]:
    try:
        if signed.get("algorithm") != "Ed25519":
            return False, "unsupported signature algorithm"
        payload = signed["payload"]
        if payload.get("policy_version") != 1:
            return False, "unsupported policy version artifact"
        if not isinstance(payload.get("policy_id"), str) or len(payload["policy_id"]) != 64:
            return False, "invalid policy id"
        if isinstance(payload.get("version"), bool) or not isinstance(payload.get("version"), int):
            return False, "invalid policy version number"
        digest = payload.get("policy_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            return False, "invalid policy digest"
        source_ref = payload.get("source_ref")
        if not isinstance(source_ref, str) or not source_ref:
            return False, "invalid policy source reference"
        expected_id = policy_id(source_ref)
        if expected_id != payload["policy_id"]:
            return False, "policy id does not match source reference"
        public_key.verify(
            base64.b64decode(signed["signature"], validate=True),
            _canonical(payload),
        )
        return True, "valid signed policy version"
    except (KeyError, TypeError, ValueError, InvalidSignature):
        return False, "invalid or tampered signed policy version"
class PolicyVersionRegistry:
    """Persist and resolve signed policy versions."""

    def __init__(self, storage):
        self.storage = storage

    def register(self, signed: SignedPolicyVersion) -> SignedPolicyVersion:
        self.storage.register_policy_version(signed.as_dict())
        return signed

    def resolve(self, policy_sha256: str) -> dict[str, Any] | None:
        return self.storage.policy_version_by_sha(policy_sha256)


@dataclass(frozen=True)
class PolicyChangeGovernanceAction:
    action_id: str
    policy_id: str
    policy_sha256: str
    version: int
    source_ref: str
    parent_sha256: str | None
    governance_policy_sha256: str
    reason: str
    issued_at: float
    expires_at: float
    nonce: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "governance_version": 1,
            "action": "POLICY_CHANGE",
            "action_id": self.action_id,
            "policy_id": self.policy_id,
            "policy_sha256": self.policy_sha256,
            "policy_version_number": self.version,
            "source_ref": self.source_ref,
            "parent_sha256": self.parent_sha256,
            "governance_policy_sha256": self.governance_policy_sha256,
            "reason": self.reason,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "nonce": self.nonce,
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.as_dict())).hexdigest()
def create_policy_change_action(
    signed_policy: dict[str, Any],
    *,
    governance_policy,
    reason: str,
    issued_at: float | None = None,
    expires_at: float | None = None,
    action_id: str | None = None,
    nonce: str | None = None,
) -> PolicyChangeGovernanceAction:
    """Create the exact governance action governors must approve."""
    governance_policy.validate()
    if "POLICY_CHANGE" not in governance_policy.allowed_actions:
        raise ValueError("governance policy does not allow policy changes")
    if not reason.strip():
        raise ValueError("policy change reason is required")
    payload = signed_policy["payload"]
    issued = time.time() if issued_at is None else issued_at
    expiry = (
        issued + governance_policy.max_approval_lifetime_seconds
        if expires_at is None
        else expires_at
    )
    if expiry <= issued or expiry - issued > governance_policy.max_approval_lifetime_seconds:
        raise ValueError("invalid policy governance action expiry")
    return PolicyChangeGovernanceAction(
        action_id=action_id or str(uuid.uuid4()),
        policy_id=payload["policy_id"],
        policy_sha256=payload["policy_sha256"],
        version=payload["version"],
        source_ref=payload["source_ref"],
        parent_sha256=payload.get("parent_sha256"),
        governance_policy_sha256=governance_policy.digest,
        reason=reason,
        issued_at=issued,
        expires_at=expiry,
        nonce=nonce or str(uuid.uuid4()),
    )
class GovernedPolicyVersionRegistry(PolicyVersionRegistry):
    """Publish signed policy versions only after governance quorum approval."""

    def publish(
        self,
        signed_policy: dict[str, Any],
        action: PolicyChangeGovernanceAction | dict[str, Any],
        approvals: list[dict[str, Any]],
        governance_policy,
        issuer_public_key: Ed25519PublicKey,
    ) -> dict[str, Any]:
        from .governance import verify_governance_quorum

        ok, reason = verify_policy_version(signed_policy, issuer_public_key)
        if not ok:
            raise PermissionError(reason)
        ok, reason = verify_governance_quorum(
            action,
            approvals,
            governance_policy,
        )
        if not ok:
            raise PermissionError(reason)
        payload = action.as_dict() if hasattr(action, "as_dict") else action
        policy_payload = signed_policy["payload"]
        if payload.get("action") != "POLICY_CHANGE":
            raise PermissionError("unsupported policy governance action")
        expected = {
            "policy_id": policy_payload["policy_id"],
            "policy_sha256": policy_payload["policy_sha256"],
            "policy_version_number": policy_payload["version"],
            "source_ref": policy_payload["source_ref"],
            "parent_sha256": policy_payload.get("parent_sha256"),
        }
        for field, value in expected.items():
            if payload.get(field) != value:
                raise PermissionError(
                    f"policy governance action does not match signed policy: {field}"
                )
        if payload.get("governance_policy_sha256") != governance_policy.digest:
            raise PermissionError("governance policy fingerprint mismatch")
        existing = self.storage.governed_policy_change_by_sha(
            policy_payload["policy_sha256"]
        )
        if existing is not None:
            raise PermissionError("governed policy version already published")
        latest = self.storage.latest_governed_policy_version(policy_payload["policy_id"])
        version = policy_payload["version"]
        parent = policy_payload.get("parent_sha256")
        if latest is None:
            if version != 1 or parent is not None:
                raise PermissionError("first governed policy version must start at 1")
        else:
            if version != latest["version"] + 1:
                raise PermissionError("governed policy version must increment monotonically")
            if parent != latest["policy_sha256"]:
                raise PermissionError("governed policy parent does not match latest version")
        envelope = {
            "policy_version": signed_policy,
            "governance_action": payload,
            "approvals": approvals,
            "governance_policy": governance_policy.as_dict(),
            "governance_policy_sha256": governance_policy.digest,
            "algorithm": "Ed25519-POLICY-MULTIPARTY",
        }
        self.storage.register_governed_policy_change(
            signed_policy,
            envelope,
            governance_approvals=approvals,
        )
        return {
            "policy": signed_policy,
            "governance_action": payload,
            "approvals": approvals,
            "governance_policy_sha256": governance_policy.digest,
        }
    def governed(self, policy_sha256: str) -> dict[str, Any] | None:
        return self.storage.governed_policy_change_by_sha(policy_sha256)
