"""Ed25519 keypair management. Private key never leaves the issuer's
process; only the public key needs to be shared for third-party
verification.
"""
from __future__ import annotations

import os
import tempfile
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


def _secure_private_key_path(path: Path) -> None:
    """Restrict the issuer key and its containing directory on POSIX hosts."""
    if os.name != "posix":
        return
    if path.is_symlink() or path.parent.is_symlink():
        raise PermissionError("issuer key path must not be a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    if path.exists():
        os.chmod(path, 0o600)


def _write_atomic(path: Path, data: bytes, mode: int) -> None:
    """Atomically replace a key file with restrictive permissions."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        os.chmod(path.parent, 0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary_path = Path(temporary_name)
    try:
        if os.name == "posix":
            os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        if os.name == "posix":
            os.chmod(path, mode)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def generate_keypair(
    private_key_path: str | Path,
    public_key_path: str | Path,
    passphrase: bytes | None = None,
) -> None:
    """Write a new Ed25519 keypair.

    The private key is encrypted at rest (PKCS#8, BestAvailableEncryption)
    when a passphrase is given or VERIGATE_KEY_PASSPHRASE is set. With
    VERIGATE_REQUIRE_ENCRYPTED_KEY=1 a plaintext key is never written.
    On POSIX systems the private key is mode 0600 in a mode-0700 directory;
    the public key is mode 0644 in that same private directory.
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

    private_path = Path(private_key_path)
    public_path = Path(public_key_path)
    if private_path.resolve() == public_path.resolve():
        raise ValueError("private and public key paths must be different")
    _write_atomic(private_path, priv_bytes, 0o600)
    _write_atomic(public_path, pub_bytes, 0o644)


def load_private_key(
    path: str | Path, passphrase: bytes | None = None
) -> Ed25519PrivateKey:
    """Load the issuer key, decrypting it if it is encrypted at rest.

    Plaintext keys still load (backward compatible) unless
    VERIGATE_REQUIRE_ENCRYPTED_KEY=1, which refuses them. Decryption is
    expensive by design, so a loaded key is cached per (file, mtime).
    Existing POSIX key files are tightened to mode 0600 before reading;
    inability to enforce these permissions fails closed.
    """
    p = Path(path)
    _secure_private_key_path(p)
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


def ensure_keypair(
    private_key_path: str | Path,
    public_key_path: str | Path,
) -> Ed25519PrivateKey:
    """Load one stable issuer identity, creating it only when neither file exists.

    A half-present or mismatched pair is corruption, not permission to rotate
    the issuer identity. Fail closed so old receipts remain verifiable and
    accounting state cannot silently acquire a new signer.
    """
    private_path = Path(private_key_path)
    public_path = Path(public_key_path)
    if private_path.resolve() == public_path.resolve():
        raise ValueError("private and public key paths must be different")
    if private_path.is_symlink() or public_path.is_symlink():
        raise PermissionError("issuer key files must not be symbolic links")

    private_exists = private_path.exists()
    public_exists = public_path.exists()
    if not private_exists and not public_exists:
        generate_keypair(private_path, public_path)
    elif private_exists != public_exists:
        raise RuntimeError(
            "incomplete issuer keypair; refusing to generate or rotate issuer identity"
        )

    private_key = load_private_key(private_path)
    public_key = load_public_key(public_path)
    private_raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    if private_raw != public_raw:
        raise RuntimeError(
            "issuer private/public keys do not match; refusing to sign with a changed identity"
        )
    return private_key
