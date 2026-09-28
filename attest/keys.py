"""Ed25519 keypair management. Private key never leaves the issuer's
process; only the public key needs to be shared for third-party
verification.
"""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


PASSPHRASE_ENV = "VERIGATE_KEY_PASSPHRASE"  # nosec B105 - env var name, not a secret
REQUIRE_ENCRYPTED_ENV = "VERIGATE_REQUIRE_ENCRYPTED_KEY"

_key_cache: dict[tuple, Ed25519PrivateKey] = {}


def _env_passphrase() -> bytes | None:
    raw = os.environ.get(PASSPHRASE_ENV)
    return raw.encode("utf-8") if raw else None


def _require_encrypted() -> bool:
    return os.environ.get(REQUIRE_ENCRYPTED_ENV, "").lower() in {"1", "true", "yes"}


def generate_keypair(
    private_key_path: str | Path,
    public_key_path: str | Path,
    passphrase: bytes | None = None,
) -> None:
    """Write a new Ed25519 keypair.

    The private key is encrypted at rest (PKCS#8, BestAvailableEncryption)
    when a passphrase is given or VERIGATE_KEY_PASSPHRASE is set. With
    VERIGATE_REQUIRE_ENCRYPTED_KEY=1 a plaintext key is never written.
    """
    passphrase = passphrase or _env_passphrase()
    if passphrase is None and _require_encrypted():
        raise RuntimeError(
            f"{REQUIRE_ENCRYPTED_ENV} is set but no passphrase is available; "
            f"set {PASSPHRASE_ENV}"
        )
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    encryption = (
        serialization.BestAvailableEncryption(passphrase)
        if passphrase
        else serialization.NoEncryption()
    )
    priv_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    )
    pub_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    Path(private_key_path).parent.mkdir(parents=True, exist_ok=True)
    Path(private_key_path).write_bytes(priv_bytes)
    Path(public_key_path).parent.mkdir(parents=True, exist_ok=True)
    Path(public_key_path).write_bytes(pub_bytes)


def load_private_key(
    path: str | Path, passphrase: bytes | None = None
) -> Ed25519PrivateKey:
    """Load the issuer key, decrypting it if it is encrypted at rest.

    Plaintext keys still load (backward compatible) unless
    VERIGATE_REQUIRE_ENCRYPTED_KEY=1, which refuses them. Decryption is
    expensive by design, so a loaded key is cached per (file, mtime).
    """
    p = Path(path)
    passphrase = passphrase or _env_passphrase()
    stat = p.stat()
    cache_key = (str(p.resolve()), stat.st_mtime_ns, stat.st_size, passphrase)
    cached = _key_cache.get(cache_key)
    if cached is not None:
        return cached
    data = p.read_bytes()
    encrypted = b"ENCRYPTED" in data.split(b"\n", 1)[0]
    if encrypted:
        if passphrase is None:
            raise ValueError(
                f"issuer key is encrypted; set {PASSPHRASE_ENV} to decrypt it"
            )
        try:
            key = serialization.load_pem_private_key(data, password=passphrase)
        except ValueError as exc:
            raise ValueError("cannot decrypt issuer key: wrong passphrase") from exc
    else:
        if _require_encrypted():
            raise ValueError(
                f"plaintext issuer key refused because {REQUIRE_ENCRYPTED_ENV} is set"
            )
        key = serialization.load_pem_private_key(data, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Key file does not contain an Ed25519 private key")
    _key_cache.clear()  # keep at most the current key in memory
    _key_cache[cache_key] = key
    return key


def load_public_key(path: str | Path) -> Ed25519PublicKey:
    data = Path(path).read_bytes()
    key = serialization.load_pem_public_key(data)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("Key file does not contain an Ed25519 public key")
    return key
