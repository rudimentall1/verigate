"""Live HTTP resource-state verification before execution."""
from __future__ import annotations

import hashlib
import urllib.request
from typing import Any, Callable


class HTTPExternalStateVerifier:
    """Verify an HTTP resource version/digest immediately before side effect.

    Binding format::
        {
          "kind": "http.state",
          "reference": "resource-id",
          "digest": "<sha256 of canonical observation>",
          "url": "https://api.example/resource/1",
          "method": "GET",
          "expected_status": 200,
          "etag": "\"v7\""
        }

    A response body digest may be used instead of ETag. The preflight request is
    read-only and is completed before the execution adapter is invoked.
    """

    def __init__(self, transport: Callable[[str, str, dict[str, str]], tuple[int, dict[str, str], bytes]] | None = None):
        self.transport = transport or self._default_transport

    @staticmethod
    def _default_transport(url: str, method: str, headers: dict[str, str]) -> tuple[int, dict[str, str], bytes]:
        request = urllib.request.Request(url, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, {str(k).lower(): str(v) for k, v in response.headers.items()}, response.read()

    @staticmethod
    def _digest(observation: dict[str, Any]) -> str:
        import json
        data = json.dumps(observation, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    def __call__(self, binding: dict[str, Any], action: dict[str, Any]) -> tuple[bool, str]:
        try:
            if binding.get("kind") != "http.state":
                return False, "unsupported HTTP state binding kind"
            url = binding.get("url")
            method = binding.get("method", "GET")
            if not isinstance(url, str) or not url.strip():
                return False, "HTTP state binding has no URL"
            if method not in {"GET", "HEAD"}:
                return False, "HTTP state preflight must be GET or HEAD"
            status, headers, body = self.transport(url, method, {"Accept": "application/json, */*"})
            expected_status = binding.get("expected_status", 200)
            if status != expected_status:
                return False, f"HTTP state status changed: expected {expected_status}, got {status}"
            observation: dict[str, Any] = {
                "kind": "http.state",
                "url": url,
                "method": method,
                "status": status,
            }
            expected_etag = binding.get("etag")
            if expected_etag is not None:
                if headers.get("etag") != expected_etag:
                    return False, "HTTP resource ETag changed"
                observation["etag"] = headers.get("etag")
            if "response_sha256" in binding:
                response_digest = hashlib.sha256(body).hexdigest()
                if response_digest != binding.get("response_sha256"):
                    return False, "HTTP response digest changed"
                observation["response_sha256"] = response_digest
            elif method != "HEAD":
                observation["response_sha256"] = hashlib.sha256(body).hexdigest()
            if self._digest(observation) != binding.get("digest"):
                return False, "HTTP external state digest changed"
            return True, "HTTP state matches authorization"
        except Exception as exc:
            return False, f"HTTP state verification failed: {exc}"
