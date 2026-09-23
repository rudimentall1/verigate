"""HTTP/API execution boundary for signed Verigate actions."""
from __future__ import annotations

from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.storage import Storage
from enforcement.local import ExecutionGate


class HTTPExecutionAdapter(ExecutionGate):
    """Execute one exact HTTP request committed by the signed ActionIntent."""

    def _request(self, authorization: dict[str, Any]) -> dict[str, Any]:
        action = authorization["payload"]["action"]
        if action.get("action_type") != "api.request":
            raise ValueError("HTTP adapter requires action_type=api.request")
        metadata = action.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("HTTP action metadata must be an object")
        method = metadata.get("method")
        url = metadata.get("url")
        if not isinstance(method, str) or not method.strip():
            raise ValueError("HTTP action has no method")
        if not isinstance(url, str) or not url.strip():
            raise ValueError("HTTP action has no URL")
        if action.get("target") != url:
            raise ValueError("HTTP action target does not match signed URL")
        headers = metadata.get("headers", {})
        if not isinstance(headers, dict):
            raise ValueError("HTTP action headers must be an object")
        return {
            "method": method.upper(),
            "url": url,
            "headers": dict(headers),
            "body": metadata.get("body"),
        }

    def execute_request(
        self,
        authorization: dict[str, Any],
        transport: Callable[[dict[str, Any]], Any],
    ) -> Any:
        """Consume authority and invoke the transport with signed request data."""
        request = self._request(authorization)
        return self.execute(authorization, lambda _action: transport(request))

    def consume(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        try:
            self._request(authorization)
        except (KeyError, TypeError, ValueError) as exc:
            return False, str(exc)
        return super().consume(authorization)
