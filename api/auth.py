"""API-key authentication for the Verigate HTTP surface.

Default-deny: once VERIGATE_API_KEYS is configured, every route requires a
key except the explicit public allowlist below (public keys, health, and the
two offline verification endpoints, whose whole point is that a third party
can call them without an account).

Keys are read from the environment on every request so rotation needs no
restart. Each entry is either a plain key or ``sha256:<hex>`` so deployments
need not keep raw keys in their environment. Comparison is constant-time.

VERIGATE_REQUIRE_AUTH=1 makes an unconfigured deployment refuse every
non-public request (fail closed) instead of running open.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from api.tenancy import DEFAULT_TENANT, TENANT_HEADER, tenant_key_mode, validate_tenant_id

PUBLIC_ROUTES = frozenset(
    {
        ("GET", "/health"),
        ("GET", "/v1/public-key"),
        ("GET", "/v1/governance/public-key"),
        ("POST", "/v1/verify"),
        ("POST", "/v1/evidence/manifest/verify"),
    }
)


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes"}


def _configured_digests() -> list[bytes]:
    digests: list[bytes] = []
    for entry in os.environ.get("VERIGATE_API_KEYS", "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        if entry.startswith("sha256:"):
            try:
                digests.append(bytes.fromhex(entry[len("sha256:"):]))
            except ValueError:
                continue  # malformed entry can never match; ignore it
        else:
            digests.append(hashlib.sha256(entry.encode("utf-8")).digest())
    return digests


def _presented_key(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header[:7].lower() == "bearer ":
        return header[7:].strip() or None
    return request.headers.get("x-api-key") or None


def is_authorized(presented: str | None) -> bool:
    if not presented:
        return False
    candidate = hashlib.sha256(presented.encode("utf-8")).digest()
    matched = False
    for digest in _configured_digests():  # no early exit: constant-time-ish
        matched |= hmac.compare_digest(candidate, digest)
    return matched


def _tenant_key_digests() -> dict[str, bytes] | None:
    raw = os.environ.get("VERIGATE_TENANT_API_KEYS")
    if not raw:
        return None
    try:
        configured = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(configured, dict) or not configured:
        return None
    result: dict[str, bytes] = {}
    for tenant_id, entry in configured.items():
        if not isinstance(tenant_id, str) or not isinstance(entry, str):
            return None
        try:
            validate_tenant_id(tenant_id)
            if entry.startswith("sha256:"):
                digest = bytes.fromhex(entry[len("sha256:"):])
                if len(digest) != hashlib.sha256().digest_size:
                    return None
            else:
                digest = hashlib.sha256(entry.encode("utf-8")).digest()
        except ValueError:
            return None
        result[tenant_id] = digest
    return result


def _tenant_authorization(request: Request) -> tuple[bool, int, str]:
    configured = _tenant_key_digests()
    if configured is None:
        return False, 401, "tenant authentication is not configured"
    tenant_id = request.headers.get(TENANT_HEADER, DEFAULT_TENANT).strip() or DEFAULT_TENANT
    try:
        validate_tenant_id(tenant_id)
    except ValueError:
        return False, 401, "invalid tenant"
    presented = _presented_key(request)
    if not presented:
        return False, 401, "missing API key"
    candidate = hashlib.sha256(presented.encode("utf-8")).digest()
    expected = configured.get(tenant_id)
    if expected is not None and hmac.compare_digest(candidate, expected):
        return True, 200, "authorized"
    if any(hmac.compare_digest(candidate, digest) for digest in configured.values()):
        return False, 403, "credential is not authorized for this tenant"
    return False, 401, "missing or invalid API key"


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        is_public = (request.method, request.url.path) in PUBLIC_ROUTES
        if is_public and not (tenant_key_mode() and request.url.path == "/v1/public-key"):
            return await call_next(request)
        if tenant_key_mode():
            authorized, status_code, detail = _tenant_authorization(request)
            if not authorized:
                return JSONResponse(
                    {"detail": detail}, status_code=status_code,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return await call_next(request)
        # "Configured" means the operator set the variable at all, not that
        # it parsed to a usable key: a typo'd VERIGATE_API_KEYS must lock the
        # API down (no key can match), never silently fall back to open.
        configured = bool(os.environ.get("VERIGATE_API_KEYS", "").strip(", "))
        if not configured:
            if _truthy("VERIGATE_REQUIRE_AUTH"):
                return JSONResponse(
                    {"detail": "authentication required but no API keys configured"},
                    status_code=401,
                )
            return await call_next(request)  # legacy open mode
        if not is_authorized(_presented_key(request)):
            return JSONResponse(
                {"detail": "missing or invalid API key"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)
