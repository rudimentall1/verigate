"""Shared attestor identity primitives that do not depend on attestation services."""

import hashlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


ATTESTOR_TYPES = frozenset({"EXECUTOR", "EXTERNAL_VERIFIER", "CHAIN_VERIFIER"})


def key_fingerprint(public_key: Ed25519PublicKey) -> str:
    """Return the SHA-256 fingerprint of a raw Ed25519 public key."""
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()
