"""Per-request tenant resolution and issuer key loading.

Backward compatible by default: without VERIGATE_TENANT_KEY_DIR set, every
call resolves exactly the way api/main.py always has -- one global issuer
key file, tenant header ignored. Setting VERIGATE_TENANT_KEY_DIR switches
every issuer key load in the API to a per-tenant keypair on disk under that
directory (see attest.key_provider.TenantKeyDirectoryProvider), selected by
the X-Verigate-Tenant request header.

The governance key is deliberately out of scope here: it is a single shared
authority across all tenants by design, not per-tenant.
"""
from __future__ import annotations

import os
from contextvars import ContextVar

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from attest.key_provider import TenantKeyDirectoryProvider
from attest.keys import load_private_key, load_public_key

TENANT_HEADER = "x-verigate-tenant"
DEFAULT_TENANT = "default"

_current_tenant: ContextVar[str] = ContextVar("verigate_tenant", default=DEFAULT_TENANT)
_provider_cache: tuple[str, TenantKeyDirectoryProvider] | None = None


def _passphrase() -> bytes | None:
    raw = os.environ.get("VERIGATE_KEY_PASSPHRASE")
    return raw.encode("utf-8") if raw else None


def _provider() -> TenantKeyDirectoryProvider | None:
    """Multi-tenant mode is off unless VERIGATE_TENANT_KEY_DIR is set."""
    global _provider_cache
    base_dir = os.environ.get("VERIGATE_TENANT_KEY_DIR")
    if not base_dir:
        return None
    if _provider_cache is None or _provider_cache[0] != base_dir:
        _provider_cache = (
            base_dir,
            TenantKeyDirectoryProvider(base_dir=base_dir, encryption_passphrase=_passphrase()),
        )
    return _provider_cache[1]


def current_tenant_id() -> str:
    return _current_tenant.get()


class TenantMiddleware(BaseHTTPMiddleware):
    """Reads X-Verigate-Tenant and exposes it via current_tenant_id() for
    the duration of the request. Harmless when multi-tenant mode is off:
    nothing reads the resolved tenant id in that case."""

    async def dispatch(self, request: Request, call_next):
        tenant_id = request.headers.get(TENANT_HEADER, DEFAULT_TENANT).strip() or DEFAULT_TENANT
        token = _current_tenant.set(tenant_id)
        try:
            return await call_next(request)
        finally:
            _current_tenant.reset(token)


def issuer_private_key(
    private_key_path: str, tenant_id: str | None = None
) -> Ed25519PrivateKey:
    """Load the issuer private key for the given (or current-request) tenant.

    Falls back to the original single-tenant file load when multi-tenant
    mode is not configured, so every existing deployment is unaffected.
    """
    provider = _provider()
    if provider is None:
        return load_private_key(private_key_path)
    return provider.get_private_key(tenant_id or current_tenant_id())


def issuer_public_key(
    public_key_path: str, tenant_id: str | None = None
) -> Ed25519PublicKey:
    provider = _provider()
    if provider is None:
        return load_public_key(public_key_path)
    return provider.get_public_key(tenant_id or current_tenant_id())
