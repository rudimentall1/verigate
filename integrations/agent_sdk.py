"""Small, framework-independent Python client helpers for Verigate agent identity.

Private keys stay on the agent host. Only the public enrollment package is
intended to be transferred to a Verigate operator.
"""
from __future__ import annotations

import base64
import hashlib
import math
import os
import re
import stat
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.identity import sign_action_intent
from core.models import ActionIntent
from integrations.arc import arc_payment_metadata


def load_or_create_agent_key(path: str | Path) -> Ed25519PrivateKey:
    """Load a 32-byte Ed25519 seed or create it with owner-only permissions."""
    key_path = Path(path).expanduser()
    key_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(key_path, flags)
    except FileNotFoundError:
        seed = Ed25519PrivateKey.generate().private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        create_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            create_flags |= os.O_NOFOLLOW
        try:
            fd = os.open(key_path, create_flags, 0o600)
        except FileExistsError:
            return load_or_create_agent_key(key_path)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(seed)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            try:
                key_path.unlink()
            except OSError:
                pass
            raise
        return Ed25519PrivateKey.from_private_bytes(seed)

    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("agent key path must be a regular file")
        if os.name == "posix" and info.st_mode & 0o077:
            raise PermissionError("agent private key file must not be accessible by group or others")
        seed = handle.read(33)
    if len(seed) != 32:
        raise ValueError("agent private key file must contain exactly 32 raw bytes")
    return Ed25519PrivateKey.from_private_bytes(seed)


def public_identity(private_key: Ed25519PrivateKey, agent_id: str) -> dict[str, str]:
    if not isinstance(agent_id, str) or not agent_id.strip() or len(agent_id) > 128:
        raise ValueError("agent_id must be a non-empty string of at most 128 characters")
    raw_public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "agent_id": agent_id,
        "identity_id": hashlib.sha256(raw_public).hexdigest(),
        "public_key_b64": base64.b64encode(raw_public).decode("ascii"),
    }


def build_arc_enrollment_package(
    private_key: Ed25519PrivateKey,
    *,
    agent_id: str,
    capability_id: str,
    allowed_targets: list[str],
    max_per_action_usdc: str | int | float | Decimal,
    expires_at: float,
    issued_at: float | None = None,
) -> dict[str, Any]:
    """Build the public-only operator enrollment package. Never includes a private key."""
    identity = public_identity(private_key, agent_id)
    if not isinstance(capability_id, str) or not capability_id.strip() or len(capability_id) > 128:
        raise ValueError("capability_id must be a non-empty string of at most 128 characters")
    if (
        not isinstance(allowed_targets, list)
        or not allowed_targets
        or any(not isinstance(target, str) or re.fullmatch(r"0x[0-9a-fA-F]{40}", target) is None for target in allowed_targets)
        or len(set(allowed_targets)) != len(allowed_targets)
    ):
        raise ValueError("allowed_targets must be a non-empty list of unique EVM addresses")
    amount = Decimal(str(max_per_action_usdc))
    if not amount.is_finite() or amount <= 0:
        raise ValueError("max_per_action_usdc must be finite and greater than zero")
    issued = time.time() if issued_at is None else float(issued_at)
    expiry = float(expires_at)
    if not math.isfinite(issued) or not math.isfinite(expiry) or not (expiry > issued):
        raise ValueError("issued_at and expires_at must be finite, with expiry later than issuance")
    return {
        "schema_version": 1,
        "agent_id": identity["agent_id"],
        "public_key_b64": identity["public_key_b64"],
        "capability_id": capability_id,
        "allowed_targets": list(allowed_targets),
        "max_per_action_usdc": format(amount, "f"),
        "issued_at": issued,
        "expires_at": expiry,
    }


def build_arc_payment_authorization_request(
    private_key: Ed25519PrivateKey,
    *,
    agent_id: str,
    identity_id: str,
    capability_id: str,
    sender: str,
    recipient: str,
    amount_usdc: str | int | float | Decimal,
    resource: str = "",
    intent_id: str | None = None,
    timestamp: float | None = None,
) -> dict[str, Any]:
    """Create the exact signed request expected by POST /v1/integrations/arc/authorize."""
    amount = Decimal(str(amount_usdc))
    if not amount.is_finite() or amount <= 0:
        raise ValueError("amount_usdc must be finite and greater than zero")
    if not isinstance(agent_id, str) or not agent_id.strip() or len(agent_id) > 128:
        raise ValueError("agent_id must be a non-empty string of at most 128 characters")
    if not identity_id or not capability_id:
        raise ValueError("identity_id and capability_id are required")
    expected_identity_id = public_identity(private_key, agent_id)["identity_id"]
    if identity_id != expected_identity_id:
        raise ValueError("identity_id does not match this agent private key")
    metadata = arc_payment_metadata(sender, recipient, amount)
    action = ActionIntent(
        agent_id=agent_id,
        action_type="payment",
        target=recipient,
        resource=resource,
        amount=amount,
        amount_exact=format(amount, "f"),
        asset="USDC",
        network="arc",
        metadata=metadata,
        **({"intent_id": intent_id} if intent_id else {}),
        **({"timestamp": timestamp} if timestamp is not None else {}),
    )
    signature = sign_action_intent(action, identity_id, private_key)
    return {
        "identity_id": identity_id,
        "capability_id": capability_id,
        "agent_id": agent_id,
        "agent_signature": signature,
        "intent_id": action.intent_id,
        "timestamp": action.timestamp,
        "action_type": action.action_type,
        "target": action.target,
        "resource": action.resource,
        "amount": float(amount),
        "amount_exact": format(amount, "f"),
        "asset": action.asset,
        "network": action.network,
        "purpose": action.purpose,
        "declared_context": action.declared_context,
        "parent_intent_id": action.parent_intent_id,
        "requested_capability": action.requested_capability,
        "constraints": action.constraints,
        "metadata": action.metadata,
    }
