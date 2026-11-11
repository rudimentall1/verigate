"""Operator-controlled enrollment and revocation for generic agent capabilities.

The enrollment package contains public identity material only. Apply it on the
Verigate API host using the same database configured for the running API.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any

from core.capabilities import CapabilityRegistry
from core.identity import IdentityRegistry
from core.models import AgentIdentity, Capability
from core.storage import Storage


_REQUIRED_FIELDS = {
    "schema_version",
    "agent_id",
    "public_key_b64",
    "capability_id",
    "allowed_actions",
    "allowed_targets",
    "allowed_resources",
    "allowed_purposes",
    "context_constraints",
    "issued_at",
    "expires_at",
}


def _string_list(value: Any, field: str, *, required: bool) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    if required and not value:
        raise ValueError(f"{field} must not be empty")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 256 for item in value):
        raise ValueError(f"{field} must contain non-empty strings of at most 256 characters")
    if len(set(value)) != len(value):
        raise ValueError(f"{field} must not contain duplicates")
    return tuple(value)


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number")
    return number


def build_enrollment(package: dict[str, Any], *, now: float | None = None):
    """Validate a strict public package and construct core identity/capability records."""
    if not isinstance(package, dict) or set(package) != _REQUIRED_FIELDS:
        raise ValueError("package must contain exactly the documented enrollment fields")
    if package["schema_version"] != 1:
        raise ValueError("unsupported enrollment schema_version")

    agent_id = package["agent_id"]
    capability_id = package["capability_id"]
    if not isinstance(agent_id, str) or not agent_id.strip() or len(agent_id) > 128:
        raise ValueError("agent_id must be a non-empty string of at most 128 characters")
    if not isinstance(capability_id, str) or not capability_id.strip() or len(capability_id) > 128:
        raise ValueError("capability_id must be a non-empty string of at most 128 characters")

    encoded_key = package["public_key_b64"]
    if not isinstance(encoded_key, str):
        raise ValueError("public_key_b64 must be a base64 string")
    try:
        raw_key = base64.b64decode(encoded_key, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("public_key_b64 is invalid") from exc
    if len(raw_key) != 32:
        raise ValueError("Ed25519 public key must be exactly 32 bytes")

    actions = _string_list(package["allowed_actions"], "allowed_actions", required=True)
    targets = _string_list(package["allowed_targets"], "allowed_targets", required=True)
    resources = _string_list(package["allowed_resources"], "allowed_resources", required=False)
    purposes = _string_list(package["allowed_purposes"], "allowed_purposes", required=False)
    constraints = package["context_constraints"]
    if not isinstance(constraints, dict):
        raise ValueError("context_constraints must be an object")

    issued_at = _finite_number(package["issued_at"], "issued_at")
    expires_at = _finite_number(package["expires_at"], "expires_at")
    now = time.time() if now is None else now
    if issued_at > now + 300:
        raise ValueError("issued_at is too far in the future")
    if expires_at <= now or expires_at <= issued_at:
        raise ValueError("enrollment package is expired or has an invalid expiry")

    identity_id = hashlib.sha256(raw_key).hexdigest()
    identity = AgentIdentity(
        agent_id=agent_id,
        public_key_b64=encoded_key,
        key_id=identity_id,
        issued_at=issued_at,
        expires_at=expires_at,
        metadata={"enrollment": "operator-agent-v1"},
    )
    capability = Capability(
        capability_id=capability_id,
        agent_id=agent_id,
        identity_id=identity_id,
        allowed_actions=actions,
        allowed_targets=targets,
        allowed_resources=resources,
        allowed_purposes=purposes,
        context_constraints=constraints,
        issued_at=issued_at,
        expires_at=expires_at,
        metadata={"enrollment": "operator-agent-v1"},
    )
    return identity, capability


def enroll(storage: Storage, package: dict[str, Any], *, now: float | None = None) -> tuple[str, str]:
    """Register the exact identity and capability; exact replay is idempotent."""
    identity, capability = build_enrollment(package, now=now)
    identities = IdentityRegistry(storage)
    capabilities = CapabilityRegistry(storage)

    existing_identity = storage.identity(identity.key_id)
    if existing_identity is not None:
        if existing_identity.digest != identity.digest:
            raise ValueError("identity_id already exists with different identity data")
        if not identities.active(identity.key_id):
            raise ValueError("identity already exists but is not active")
    else:
        identities.register(identity)

    existing_capability = storage.capability(capability.capability_id)
    if existing_capability is not None:
        if existing_capability.digest != capability.digest:
            raise ValueError("capability_id already exists with different authority")
        if not capabilities.active(capability.capability_id):
            raise ValueError("capability already exists but is not active")
    else:
        try:
            capabilities.register(capability)
        except Exception:
            if existing_identity is None:
                identities.revoke(identity.key_id)
            raise

    return identity.key_id, capability.capability_id


def revoke(storage: Storage, identity_id: str, capability_id: str) -> None:
    if not identity_id or not capability_id:
        raise ValueError("both identity_id and capability_id are required")
    CapabilityRegistry(storage).revoke(capability_id)
    IdentityRegistry(storage).revoke(identity_id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.environ.get("VERIGATE_DB", "data/verigate.db"))
    parser.add_argument("--package", help="Path to operator-approved public enrollment JSON")
    parser.add_argument("--revoke-identity")
    parser.add_argument("--revoke-capability")
    args = parser.parse_args()

    if args.package and (args.revoke_identity or args.revoke_capability):
        parser.error("choose --package or revocation arguments, not both")
    if bool(args.revoke_identity) != bool(args.revoke_capability):
        parser.error("revocation requires both --revoke-identity and --revoke-capability")
    if not args.package and not args.revoke_identity:
        parser.error("provide --package or both revocation arguments")

    storage = Storage(Path(args.db))
    try:
        if args.package:
            package = json.loads(Path(args.package).read_text(encoding="utf-8"))
            identity_id, capability_id = enroll(storage, package)
            print(json.dumps({"identity_id": identity_id, "capability_id": capability_id}))
        else:
            revoke(storage, args.revoke_identity, args.revoke_capability)
            print(json.dumps({
                "revoked_identity_id": args.revoke_identity,
                "revoked_capability_id": args.revoke_capability,
            }))
    finally:
        storage.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
