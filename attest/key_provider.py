"""Issuer key provider abstraction for multi-tenant deployments.

Verigate mints authority artifacts (decisions, authorizations, evidence
manifests) using an Ed25519 issuer keypair. Every existing entry point
(api/main.py, cli.py) loads that key from one hardcoded file path -- a
single-tenant deployment. This module adds a provider seam so a
deployment can serve multiple tenants, each with its own issuer key,
without touching core/ or breaking the single-tenant call sites that
still work exactly as before.

Nothing here requires a paid KMS. `TenantKeyDirectoryProvider` is the
recommended default for a self-hosted, zero-budget deployment: one
Ed25519 keypair file per tenant, optionally encrypted at rest with a
passphrase-derived key (still no external service, just the
`cryptography` dependency this project already has).

`DerivedMultiTenantKeyProvider` is an alternative that derives every
tenant's key from one master secret instead of persisting N key files --
useful only if you cannot persist per-tenant secrets at all (e.g. a
fully stateless deployment). Prefer `TenantKeyDirectoryProvider`
otherwise: a leaked master secret in the derived provider compromises
every tenant's issuer identity at once, whereas leaking one tenant's key
file compromises only that tenant.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from attest.keys import generate_keypair, load_private_key

_PBKDF2_ITERATIONS = 200_000
_TENANT_SALT_PREFIX = b"verigate-tenant-key-v1:"


class IssuerKeyProvider(Protocol):
    """Resolves the Ed25519 issuer private key for a given tenant."""

    def get_private_key(self, tenant_id: str) -> Ed25519PrivateKey: ...


def _validate_tenant_id(tenant_id: str) -> None:
    if not tenant_id or "/" in tenant_id or "\\" in tenant_id or ".." in tenant_id:
        raise ValueError(f"invalid tenant_id: {tenant_id!r}")


def _derive_fernet(passphrase: bytes, tenant_id: str) -> Fernet:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_TENANT_SALT_PREFIX + tenant_id.encode("utf-8"),
        iterations=_PBKDF2_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase))
    return Fernet(key)


@dataclass
class LocalFileKeyProvider:
    """Current single-tenant behavior, unchanged. `tenant_id` is ignored;
    this exists purely so single-tenant and multi-tenant call sites can
    share one interface."""

    private_key_path: str

    def get_private_key(self, tenant_id: str) -> Ed25519PrivateKey:
        return load_private_key(self.private_key_path)


@dataclass
class TenantKeyDirectoryProvider:
    """One Ed25519 keypair file per tenant under `base_dir`, generated on
    first use. Recommended default for a self-hosted multi-tenant
    deployment with no KMS budget.

    If `encryption_passphrase` is set, the private key bytes are stored
    encrypted at rest (Fernet, PBKDF2-derived per-tenant key) instead of
    the bare PEM `attest.keys.generate_keypair` writes by default.
    """

    base_dir: str
    encryption_passphrase: bytes | None = None
    _cache: dict = field(default_factory=dict, repr=False)

    def _paths(self, tenant_id: str) -> tuple[Path, Path]:
        _validate_tenant_id(tenant_id)
        tenant_dir = Path(self.base_dir) / tenant_id
        return tenant_dir / "issuer.key", tenant_dir / "issuer.pub"

    def get_private_key(self, tenant_id: str) -> Ed25519PrivateKey:
        if tenant_id in self._cache:
            return self._cache[tenant_id]
        priv_path, pub_path = self._paths(tenant_id)
        if not priv_path.exists():
            priv_path.parent.mkdir(parents=True, exist_ok=True)
            generate_keypair(priv_path, pub_path)
            if self.encryption_passphrase:
                self._encrypt_in_place(priv_path, tenant_id)
        key = (
            self._load_encrypted(priv_path, tenant_id)
            if self.encryption_passphrase
            else load_private_key(priv_path)
        )
        self._cache[tenant_id] = key
        return key

    def _encrypt_in_place(self, priv_path: Path, tenant_id: str) -> None:
        fernet = _derive_fernet(self.encryption_passphrase, tenant_id)
        plaintext = priv_path.read_bytes()
        priv_path.write_bytes(fernet.encrypt(plaintext))

    def _load_encrypted(self, priv_path: Path, tenant_id: str) -> Ed25519PrivateKey:
        fernet = _derive_fernet(self.encryption_passphrase, tenant_id)
        try:
            plaintext = fernet.decrypt(priv_path.read_bytes())
        except InvalidToken as exc:
            raise ValueError(
                f"cannot decrypt issuer key for tenant {tenant_id!r}: "
                "wrong passphrase or corrupted file"
            ) from exc
        key = serialization.load_pem_private_key(plaintext, password=None)
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("decrypted key is not an Ed25519 private key")
        return key


@dataclass
class DerivedMultiTenantKeyProvider:
    """Derives a distinct Ed25519 seed per tenant from one master secret
    (PBKDF2-SHA256, tenant_id-bound salt) instead of persisting per-tenant
    key files. No paid KMS required. See module docstring for why
    `TenantKeyDirectoryProvider` is the safer default.
    """

    master_secret: bytes
    _cache: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if len(self.master_secret) < 32:
            raise ValueError("master_secret must be at least 32 bytes")

    def get_private_key(self, tenant_id: str) -> Ed25519PrivateKey:
        _validate_tenant_id(tenant_id)
        if tenant_id in self._cache:
            return self._cache[tenant_id]
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=_TENANT_SALT_PREFIX + tenant_id.encode("utf-8"),
            iterations=_PBKDF2_ITERATIONS,
        )
        seed = kdf.derive(self.master_secret)
        key = Ed25519PrivateKey.from_private_bytes(seed)
        self._cache[tenant_id] = key
        return key

    @classmethod
    def from_env(
        cls, env_var: str = "VERIGATE_TENANT_MASTER_SECRET"
    ) -> "DerivedMultiTenantKeyProvider":
        """Reads the master secret from `env_var`.

        A plain string (e.g. a 32+ character passphrase) is used verbatim
        as UTF-8 bytes. Prefix the value with ``base64:`` to supply raw
        high-entropy bytes instead, e.g. the output of
        ``python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"``.
        There is deliberately no auto-detection here: an ordinary
        passphrase can itself decode as valid base64, which would
        silently truncate it to the wrong byte string.
        """
        raw = os.environ.get(env_var)
        if not raw:
            raise RuntimeError(f"{env_var} is not set")
        if raw.startswith("base64:"):
            secret = base64.b64decode(raw[len("base64:") :], validate=True)
        else:
            secret = raw.encode("utf-8")
        return cls(master_secret=secret)
