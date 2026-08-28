"""Ed25519 keypair management. Private key never leaves the issuer's
process; only the public key needs to be shared for third-party
verification.
"""
from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def generate_keypair(private_key_path: str | Path, public_key_path: str | Path) -> None:
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    Path(private_key_path).parent.mkdir(parents=True, exist_ok=True)
    Path(private_key_path).write_bytes(priv_bytes)
    Path(public_key_path).parent.mkdir(parents=True, exist_ok=True)
    Path(public_key_path).write_bytes(pub_bytes)


def load_private_key(path: str | Path) -> Ed25519PrivateKey:
    data = Path(path).read_bytes()
    key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Key file does not contain an Ed25519 private key")
    return key


def load_public_key(path: str | Path) -> Ed25519PublicKey:
    data = Path(path).read_bytes()
    key = serialization.load_pem_public_key(data)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Key file does not contain an Ed25519 public key")
    return key
