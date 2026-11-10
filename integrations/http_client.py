"""Small dependency-free HTTP client for the Verigate Agent API.

The client transports signed intents and execution authorizations. It does not
hold issuer keys, create policy decisions, broadcast transactions, or execute
the protected side effect on the caller's behalf.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class VerigateError(RuntimeError):
    """Base exception for client-side and transport failures."""


class VerigateTransportError(VerigateError):
    """The API could not be reached or returned an unreadable response."""


class VerigateAPIError(VerigateError):
    """The API returned a non-success HTTP status."""

    def __init__(self, status_code: int, detail: Any, body: Any = None):
        self.status_code = status_code
        self.detail = detail
        self.body = body
        super().__init__(f"Verigate API returned HTTP {status_code}: {detail}")


class VerigateClient:
    """Minimal synchronous client for signed action authorization."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        tenant_id: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url must be a non-empty URL")
        normalized = base_url.strip().rstrip("/")
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self.base_url = normalized
        self.api_key = api_key
        self.tenant_id = tenant_id
        self.timeout = float(timeout)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not path.startswith("/") or ".." in path.split("/"):
            raise ValueError("path must be an absolute API path without traversal")
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.tenant_id:
            headers["X-Verigate-Tenant"] = self.tenant_id
        request = Request(self.base_url + path, data=body, headers=headers, method="POST")

        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                status = response.status
        except HTTPError as exc:
            raw = exc.read()
            try:
                parsed = json.loads(raw.decode("utf-8")) if raw else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed = {"detail": raw.decode("utf-8", errors="replace")}
            detail = parsed.get("detail", parsed) if isinstance(parsed, dict) else parsed
            raise VerigateAPIError(exc.code, detail, parsed) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise VerigateTransportError(f"Could not reach Verigate API: {exc}") from exc

        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VerigateTransportError("Verigate returned a non-JSON response") from exc
        if status < 200 or status >= 300:
            detail = result.get("detail", result) if isinstance(result, dict) else result
            raise VerigateAPIError(status, detail, result)
        if not isinstance(result, dict):
            raise VerigateTransportError("Verigate returned an unexpected JSON shape")
        return result

    def authorize_action(self, signed_intent: dict[str, Any]) -> dict[str, Any]:
        """Submit an agent-signed ActionIntent to /v1/actions/authorize."""
        return self._post("/v1/actions/authorize", signed_intent)

    def consume_execution(self, execution_authorization: dict[str, Any]) -> dict[str, Any]:
        """Consume a one-time authorization at /v1/execution/consume."""
        if not isinstance(execution_authorization, dict):
            raise TypeError("execution_authorization must be a dictionary")
        return self._post(
            "/v1/execution/consume",
            {"authorization": execution_authorization},
        )

    def authorize_and_consume(self, signed_intent: dict[str, Any]) -> dict[str, Any]:
        """Authorize and consume once; never execute the protected side effect."""
        authorization_result = self.authorize_action(signed_intent)
        receipt = authorization_result.get("decision_receipt")
        receipt_payload = receipt.get("payload") if isinstance(receipt, dict) else None
        decision = receipt_payload.get("decision") if isinstance(receipt_payload, dict) else None
        execution_authorization = authorization_result.get("execution_authorization")
        if decision != "ALLOW" or not isinstance(execution_authorization, dict):
            return {
                "authorized": False,
                "authorization": authorization_result,
                "consumption": None,
            }
        consumption = self.consume_execution(execution_authorization)
        return {
            "authorized": True,
            "authorization": authorization_result,
            "consumption": consumption,
        }
