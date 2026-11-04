"""Verigate execution adapter for Valta's OpenAI-compatible proxy.

The adapter binds the exact canonical Chat Completions request into a signed
ActionIntent. ExecutionRouter validates that binding and consumes the
one-time ExecutionAuthorization before the caller can send the request to
Valta. This module does not create wallets, move funds, or retry requests.
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from typing import Any, Callable
from urllib.parse import urlparse

from core.models import ActionIntent

VALTA_CHAT_COMPLETIONS_URL = "https://valta.co/v1/chat/completions"
ACTION_TYPE = "valta.chat_completions"
PURPOSE = "ai_inference"
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
_MAX_RESPONSE_BYTES = 8 *  1024 * 1024


class ValtaProxyError(RuntimeError):
    """A Valta proxy failure. Requests are never retried automatically."""

    def __init__(self, message: str, *, status_code: int | None = None, response: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response


def canonical_request_bytes(request: dict[str, Any]) -> bytes:
    """Serialize an OpenAI Chat Completions request deterministically."""
    if not isinstance(request, dict):
        raise TypeError("Valta request must be a JSON object")
    try:
        return json.dumps(
            request,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Valta request is not canonical JSON: {exc}") from exc


def _validate_run_id(run_id: str) -> None:
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise ValueError("run_id must be 1-200 characters: letters, digits, dot, underscore, colon or hyphen")


def _parse_chat_request(request_body: bytes) -> dict[str, Any]:
    if not isinstance(request_body, bytes) or not request_body:
        raise ValueError("Valta request body must be non-empty bytes")
    try:
        request = json.loads(request_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Valta request body must be valid UTF-8 JSON") from exc
    if not isinstance(request, dict):
        raise ValueError("Valta Chat Completions body must be a JSON object")
    if not isinstance(request.get("model"), str) or not request["model"].strip():
        raise ValueError("Valta Chat Completions requires a model")
    messages = request.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("Valta Chat Completions requires a non-empty messages array")
    if request.get("stream", False) is True:
        raise ValueError("Valta proxy pilot supports non-streaming Chat Completions only")
    return request


def action_for_chat_completion(*, agent_id: str, run_id: str, request: dict[str, Any]) -> ActionIntent:
    """Create the exact action that the agent must sign before authorization."""
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise ValueError("agent_id is required")
    _validate_run_id(run_id)
    body = canonical_request_bytes(request)
    _parse_chat_request(body)
    digest = hashlib.sha256(body).hexdigest()
    return ActionIntent(
        agent_id=agent_id,
        action_type=ACTION_TYPE,
        target=VALTA_CHAT_COMPLETIONS_URL,
        resource=run_id,
        purpose=PURPOSE,
        declared_context={"provider": "openai", "interface": "chat.completions"},
        metadata={
            "destination": VALTA_CHAT_COMPLETIONS_URL,
            "valta_proxy": {
                "method": "POST",
                "url": VALTA_CHAT_COMPLETIONS_URL,
                "run_id": run_id,
                "request_sha256": digest,
                "request_format": "openai-chat-completions",
            },
        },
    )


class ValtaProxyExecutionAdapter:
    """ExecutionRouter adapter that verifies the exact request before dispatch.

    Instantiate one adapter per request. The actual HTTP client is supplied as
    the router's side-effect callback, so this class never handles or stores
    the virtual-key secret.
    """

    execution_external_state_scope = "none"
    execution_enforcement_scope = "direct"

    def __init__(self, request_body: bytes, run_id: str) -> None:
        _validate_run_id(run_id)
        _parse_chat_request(request_body)
        self.request_body = request_body
        self.run_id = run_id
        self.request_sha256 = hashlib.sha256(request_body).hexdigest()

    def validate(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        try:
            payload = authorization["payload"]
            action = payload["action"]
            details = action["metadata"]["valta_proxy"]
        except (KeyError, TypeError):
            return False, "authorization is missing the Valta action binding"

        if action.get("action_type") != ACTION_TYPE:
            return False, "authorization is not for a Valta Chat Completions action"
        if action.get("target") != VALTA_CHAT_COMPLETIONS_URL:
            return False, "authorized target is not the Valta Chat Completions endpoint"
        if action.get("resource") != self.run_id:
            return False, "Valta run_id does not match the authorized action"
        metadata = action.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("destination") != VALTA_CHAT_COMPLETIONS_URL:
            return False, "Valta destination does not match the authorized endpoint"
        if details.get("method") != "POST" or details.get("url") != VALTA_CHAT_COMPLETIONS_URL:
            return False, "Valta method or URL does not match the authorized endpoint"
        if details.get("request_format") != "openai-chat-completions":
            return False, "unsupported Valta request format"
        if details.get("run_id") != self.run_id:
            return False, "Valta run_id does not match the signed metadata"
        if details.get("request_sha256") != self.request_sha256:
            return False, "Valta request body differs from the signed action"
        return True, "Valta request matches the signed action"

    def execute_after_consume(self, authorization: dict[str, Any], side_effect: Callable[[dict[str, Any]], Any]) -> Any:
        # ExecutionRouter calls this only after it has verified and consumed
        # the one-time authorization.
        return side_effect(authorization)

    def consume(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        raise RuntimeError("Verigate ExecutionRouter must own one-time authorization consumption")

    def execute(self, authorization: dict[str, Any], side_effect: Callable[[dict[str, Any]], Any]) -> Any:
        raise RuntimeError("call ExecutionRouter.execute(); direct adapter execution is disabled")

    def execute_bound(self, authorization: dict[str, Any], external_state: dict[str, Any], side_effect: Callable[[dict[str, Any]], Any]) -> Any:
        raise RuntimeError("Valta Chat Completions adapter does not support atomic external-state execution")

    def execute_bound_after_consume(self, authorization: dict[str, Any], external_state: dict[str, Any], side_effect: Callable[[dict[str, Any]], Any]) -> Any:
        raise RuntimeError("Valta Chat Completions adapter does not support atomic external-state execution")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        # Never forward a Valta virtual key to a redirect target.
        return None


class ValtaProxyClient:
    """Small, no-retry HTTP client for Valta's non-streaming proxy endpoint."""

    def __init__(self, virtual_key: str, *, timeout: float = 30.0) -> None:
        if not isinstance(virtual_key, str) or not virtual_key.startswith("vk_live_"):
            raise ValueError("a Valta live virtual key (vk_live_...) is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        parsed = urlparse(VALTA_CHAT_COMPLETIONS_URL)
        if parsed.scheme != "https" or parsed.hostname != "valta.co":
            raise ValueError("Valta proxy URL must remain the fixed HTTPS Valta endpoint")
        self._virtual_key = virtual_key
        self._timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirectHandler())

    def chat_completions(self, request_body: bytes, run_id: str) -> dict[str, Any]:
        _validate_run_id(run_id)
        _parse_chat_request(request_body)
        request = urllib.request.Request(
            VALTA_CHAT_COMPLETIONS_URL,
            data=request_body,
            headers={
                "Authorization": f"Bearer {self._virtual_key}",
                "Content-Type": "application/json",
                "X-Valta-Run-Id": run_id,
            },
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read(_MAX_RESPONSE_BYTES + 1)
            parsed_response: Any = None
            try:
                parsed_response = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed_response = raw[:2048].decode("utf-8", errors="replace")
            raise ValtaProxyError(
                f"Valta proxy returned HTTP {exc.code}",
                status_code=exc.code,
                response=parsed_response,
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            # Outcome can be uncertain after dispatch. Do not retry.
            raise ValtaProxyError(
                "Valta proxy request failed or timed out; outcome may be uncertain, do not retry automatically"
            ) from exc

        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ValtaProxyError("Valta proxy response exceeded the configured response-size limit")
        if status < 200 or status >= 300:
            raise ValtaProxyError(f"Valta proxy returned HTTP {status}", status_code=status)
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValtaProxyError("Valta proxy returned a non-JSON response", status_code=status) from exc
        if not isinstance(result, dict):
            raise ValtaProxyError("Valta proxy returned an unexpected response shape", status_code=status)
        return result
