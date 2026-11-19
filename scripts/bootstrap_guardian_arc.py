#!/usr/bin/env python3
"""Provision a narrowly scoped Verigate identity for Guardian's Arc demo.

Run from the Verigate repository root with the SAME VERIGATE_DB value that the
Arc API service will use:

    VERIGATE_DB=/opt/verigate/arc-test/verigate.db \
    PYTHONPATH=. python scripts/bootstrap_guardian_arc.py \
      --private-key-path /etc/agentic-wallet-guardian/verigate-agent-ed25519.pem

The Ed25519 private key is written once (mode 0600) and is never printed.
The identity and capability registrations are idempotent. Existing records
with conflicting key material or capability scope cause a hard failure.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.capabilities import CapabilityRegistry
from core.identity import IdentityRegistry
from core.models import AgentIdentity, Capability
from core.storage import Storage


def load_or_create_key(path: Path) -> Ed25519PrivateKey:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise SystemExit(f"Refusing non-Ed25519 key at {path}")
        return key

    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(str(path), flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(pem)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return key


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-id", default="guardian-arc-agent")
    parser.add_argument("--capability-id", default="guardian-arc-usdc-mainnet")
    parser.add_argument(
        "--private-key-path",
        default="/etc/agentic-wallet-guardian/verigate-agent-ed25519.pem",
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("VERIGATE_DB", "data/verigate.db"),
        help="Verigate database path; must match the API service database",
    )
    parser.add_argument(
        "--max-usdc",
        type=float,
        default=5.0,
        help="Capability base per-action USDC limit (dynamic probation starts at 10%%)",
    )
    parser.add_argument(
        "--allowed-target",
        action="append",
        default=[],
        help="Optional exact recipient allowlist; omit to allow any recipient up to the capability limit",
    )
    args = parser.parse_args()

    if args.max_usdc <= 0:
        parser.error("--max-usdc must be positive")

    key_path = Path(args.private_key_path)
    private_key = load_or_create_key(key_path)
    raw_public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_key_b64 = base64.b64encode(raw_public_key).decode("ascii")
    identity_id = hashlib.sha256(raw_public_key).hexdigest()

    identity = AgentIdentity(
        agent_id=args.agent_id,
        public_key_b64=public_key_b64,
        key_id=identity_id,
        metadata={"purpose": "Guardian Arc USDC payment authorization"},
    )
    capability = Capability(
        capability_id=args.capability_id,
        agent_id=args.agent_id,
        identity_id=identity_id,
        allowed_actions=("payment",),
        allowed_targets=tuple(value.lower() for value in args.allowed_target),
        allowed_networks=("arc",),
        allowed_assets=("USDC",),
        max_per_action={"USDC": args.max_usdc},
        metadata={"purpose": "Guardian Arc mainnet USDC demo"},
    )

    storage = Storage(args.db)
    try:
        identity_registry = IdentityRegistry(storage)
        existing_identity = storage.identity(identity_id)
        if existing_identity is None:
            identity_registry.register(identity)
        elif (
            existing_identity.agent_id != identity.agent_id
            or existing_identity.public_key_b64 != identity.public_key_b64
        ):
            raise SystemExit("Identity ID exists with different agent/key material")

        capability_registry = CapabilityRegistry(storage)
        existing_capability = storage.capability(args.capability_id)
        if existing_capability is None:
            capability_registry.register(capability)
        else:
            same_scope = (
                existing_capability.agent_id == capability.agent_id
                and existing_capability.identity_id == capability.identity_id
                and tuple(existing_capability.allowed_actions) == capability.allowed_actions
                and tuple(existing_capability.allowed_targets) == capability.allowed_targets
                and tuple(existing_capability.allowed_networks) == capability.allowed_networks
                and tuple(existing_capability.allowed_assets) == capability.allowed_assets
                and dict(existing_capability.max_per_action) == capability.max_per_action
            )
            if not same_scope:
                raise SystemExit(
                    "Capability ID already exists with a different scope; use a new capability ID"
                )
    finally:
        storage.close()

    print(f"VERIGATE_AGENT_ID={args.agent_id}")
    print(f"VERIGATE_IDENTITY_ID={identity_id}")
    print(f"VERIGATE_CAPABILITY_ID={args.capability_id}")
    print(f"VERIGATE_AGENT_PRIVATE_KEY_PATH={key_path}")
    print(f"VERIGATE_DB={args.db}")
    print(
        "CAPABILITY_SCOPE=payment,network=arc,asset=USDC,"
        f"max_per_action={args.max_usdc},targets="
        + (",".join(capability.allowed_targets) if capability.allowed_targets else "any")
    )
    print(
        "NOTE=Dynamic authority starts in PROBATION (10% multiplier); "
        f"initial effective USDC cap is {args.max_usdc * 0.10:.2f}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
