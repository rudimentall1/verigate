"""Cryptographically signed policy versions for Verigate authority decisions."""
from __future__ import annotations

import base64
import hashlib
import json
import time
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
