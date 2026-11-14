"""Verigate execution adapter for Valta's OpenAI-compatible proxy.

The adapter binds the exact canonical Chat Completions request into a signed
ActionIntent. ExecutionRouter validates that binding and consumes the
one-time ExecutionAuthorization before this adapter's private client can send
the request to Valta. This module does not create wallets or move funds.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import urllib.error
import urllib.request
from typing import Any, Callable
from urllib.parse import urlparse

from core.models import ActionIntent
from enforcement.protocol import ExecutionPermit

VALTA_CHAT_COMPLETIONS_URL = "https://valta.co/v1/chat/completions"
ACTION_TYPE = "valta.chat_completions"
PURPOSE = "ai_inference"
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_MAX_REQUEST_BYTES = 1024 * 1024
_MAX_COMPLETION_TOKENS = 256


class ValtaProxyError(RuntimeError):
    """A Valta proxy failure. Requests are never retried automatically."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response: Any = None,
        outcome_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response
        self.outcome_unknown = outcome_unknown


def canonical_request_bytes(request: dict[str, Any]) -> bytes:
    """Serialize an OpenAI Chat Completions request deterministically."""
    if not isinstance(request, dict):
        raise TypeError("Valta request must be a JSON object")
    try:
        encoded = json.dumps(
            request,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        if len(encoded) > _MAX_REQUEST_BYTES:
            raise ValueError("Valta pilot request exceeds the 1 MiB request limit")
        return encoded
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
    limits = [
        request[name]
        for name in ("max_tokens", "max_completion_tokens")
        if name in request
    ]
    if not limits:
        raise ValueError("Valta pilot requires an explicit max_tokens or max_completion_tokens budget")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in limits):
        raise ValueError("Valta completion token budget must be an integer")
    if any(value < 1 or value > _MAX_COMPLETION_TOKENS for value in limits):
        raise ValueError(f"Valta pilot completion token budget must be between 1 and {_MAX_COMPLETION_TOKENS}")
    if len(limits) == 2 and limits[0] != limits[1]:
        raise ValueError("max_tokens and max_completion_tokens must match when both are supplied")
    n = request.get("n", 1)
    if isinstance(n, bool) or not isinstance(n, int) or n != 1:
        raise ValueError("Valta pilot permits exactly one completion choice (n=1)")
    return request


def action_for_chat_completion(
    *,
    agent_id: str,
    run_id: str,
    request: dict[str, Any],
    intent_id: str | None = None,
    timestamp: float | None = None,
) -> ActionIntent:
    """Create the exact action that the agent must sign before authorization.

    API consumers supply intent_id and timestamp so the server reconstructs
    the same signed ActionIntent. Local callers may omit them.
    """
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise ValueError("agent_id is required")
    if intent_id is not None and (not isinstance(intent_id, str) or not intent_id.strip()):
        raise ValueError("intent_id must be a non-empty string")
    if timestamp is not None and (not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp) or timestamp <= 0):
        raise ValueError("timestamp must be a finite positive Unix timestamp")
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
        **({"intent_id": intent_id} if intent_id is not None else {}),
        **({"timestamp": float(timestamp)} if timestamp is not None else {}),
    )


class ValtaProxyExecutionAdapter:
    """ExecutionRouter adapter that verifies and sends the exact signed request.

    Instantiate one adapter per request. Its client owns the virtual key and
    request dispatch. The router's generic callback is deliberately ignored;
    this prevents a caller from validating one body but forwarding another.
    """

    execution_external_state_scope = "none"
    execution_enforcement_scope = "direct"

    def __init__(self, request_body: bytes, run_id: str, client: Any) -> None:
        _validate_run_id(run_id)
        _parse_chat_request(request_body)
        if not callable(getattr(client, "chat_completions", None)):
            raise TypeError("client must provide chat_completions(request_body, run_id)")
        self.request_body = request_body
        self.run_id = run_id
        self.request_sha256 = hashlib.sha256(request_body).hexdigest()
        self.client = client

    def validate(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        authorization = copy.deepcopy(authorization)
        try:
            payload = authorization["payload"]
            action = payload["action"]
            details = action["metadata"]["valta_proxy"]
        except (KeyError, TypeError):
            return False, "authorization is missing the Valta action binding"

        if not isinstance(action, dict) or not isinstance(details, dict):
            return False, "Valta authorization binding has an invalid shape"

        if action.get("action_type") != ACTION_TYPE or action.get("purpose") != PURPOSE:
            return False, "authorization is not for a Valta AI inference action"
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

    def execute_after_consume(
        self,
        authorization: dict[str, Any],
        side_effect: Callable[[dict[str, Any]], Any],
        *,
        permit: ExecutionPermit,
    ) -> Any:
        # Snapshot before permit claim, matching the other execution adapters.
        # A direct call without a router-issued, one-shot permit is rejected.
        authorization = copy.deepcopy(authorization)
        permit.claim(authorization)
        return self.client.chat_completions(self.request_body, self.run_id)

    def consume(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        raise RuntimeError("Verigate ExecutionRouter must own one-time authorization consumption")

    def execute(self, authorization: dict[str, Any], side_effect: Callable[[dict[str, Any]], Any]) -> Any:
        raise RuntimeError("call ExecutionRouter.execute(); direct adapter execution is disabled")

    def execute_bound(self, authorization: dict[str, Any], external_state: dict[str, Any], side_effect: Callable[[dict[str, Any]], Any]) -> Any:
        raise RuntimeError("Valta Chat Completions adapter does not support atomic external-state execution")

    def execute_bound_after_consume(self, authorization: dict[str, Any], external_state: dict[str, Any], side_effect: Callable[[dict[str, Any]], Any], *, permit: ExecutionPermit) -> Any:
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
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a finite positive number")
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
                "Valta proxy request failed or timed out; outcome may be uncertain, do not retry automatically",
                outcome_unknown=True,
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
