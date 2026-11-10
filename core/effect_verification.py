"""Independent effect verification contracts and protocol-specific evidence builders.

An executor reports what it attempted. An EffectVerifier observes the external
result and emits a deterministic observation that can be attached to an
OutcomeClaim. Verifiers never mint authority by themselves.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class ObservedEffect:
    verifier_type: str
    evidence_kind: str
    effect_status: str
    authorization_id: str
    action_sha256: str
    observed_at: float
    evidence_ref: str
    result_sha256: str
    observation: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_version": 1,
            "verifier_type": self.verifier_type,
            "evidence_kind": self.evidence_kind,
            "effect_status": self.effect_status,
            "authorization_id": self.authorization_id,
            "action_sha256": self.action_sha256,
            "observed_at": self.observed_at,
            "evidence_ref": self.evidence_ref,
            "result_sha256": self.result_sha256,
            "observation": self.observation,
            "observation_sha256": digest({
                "verifier_type": self.verifier_type,
                "evidence_kind": self.evidence_kind,
                "effect_status": self.effect_status,
                "authorization_id": self.authorization_id,
                "action_sha256": self.action_sha256,
                "observed_at": self.observed_at,
                "evidence_ref": self.evidence_ref,
                "result_sha256": self.result_sha256,
                "observation": self.observation,
            }),
        }


def _binding(authorization: dict[str, Any]) -> tuple[str, str]:
    payload = authorization["payload"]
    return payload["authorization_id"], payload["action_sha256"]


class EffectVerifier:
    verifier_type = "BASE"
    evidence_kind = "EXTERNAL_REFERENCE"

    def observe(
        self,
        authorization: dict[str, Any],
        *,
        observation: dict[str, Any],
        evidence_ref: str,
        result: Any,
        status: str,
        observed_at: float | None = None,
    ) -> ObservedEffect:
        if status not in {"SUCCEEDED", "FAILED", "UNKNOWN"}:
            raise ValueError("invalid observed effect status")
        authorization_id, action_sha256 = _binding(authorization)
        if not evidence_ref:
            raise ValueError("evidence_ref is required")
        return ObservedEffect(
            verifier_type=self.verifier_type,
            evidence_kind=self.evidence_kind,
            effect_status=status,
            authorization_id=authorization_id,
            action_sha256=action_sha256,
            observed_at=time.time() if observed_at is None else observed_at,
            evidence_ref=evidence_ref,
            result_sha256=digest(result),
            observation=observation,
        )


class HTTPResponseVerifier(EffectVerifier):
    """Independently verify an HTTP response against the signed request."""

    verifier_type = "HTTP_VERIFIER"
    evidence_kind = "HTTP_RESPONSE"

    def verify_response(
        self,
        authorization: dict[str, Any],
        response: dict[str, Any],
        *,
        evidence_ref: str,
        observed_at: float | None = None,
    ) -> ObservedEffect:
        action = authorization["payload"]["action"]
        if action.get("action_type") != "api.request":
            raise ValueError("HTTP verifier requires action_type=api.request")
        metadata = action.get("metadata") or {}
        expected_url = metadata.get("url")
        expected_method = str(metadata.get("method", "")).upper()
        if response.get("url") != expected_url:
            raise ValueError("observed URL does not match authorized URL")
        if str(response.get("method", "")).upper() != expected_method:
            raise ValueError("observed method does not match authorized method")
        status_code = response.get("status_code")
        if not isinstance(status_code, int) or not 100 <= status_code <= 599:
            raise ValueError("invalid HTTP status code")
        headers = response.get("headers", {})
        body = response.get("body")
        observation = {
            "url": response["url"],
            "method": str(response["method"]).upper(),
            "status_code": status_code,
            "headers_sha256": digest(headers),
            "body_sha256": digest(body),
        }
        return self.observe(
            authorization,
            observation=observation,
            evidence_ref=evidence_ref,
            result={"headers": headers, "body": body, "status_code": status_code},
            status="SUCCEEDED" if 200 <= status_code < 400 else "FAILED",
            observed_at=observed_at,
        )


class MCPToolVerifier(EffectVerifier):
    """Independently verify an MCP-style tool result against the signed target."""

    verifier_type = "MCP_VERIFIER"
    evidence_kind = "MCP_RESULT"

    def verify_result(
        self,
        authorization: dict[str, Any],
        *,
        tool_name: str,
        result: Any,
        evidence_ref: str,
        target_identity: str | None = None,
        observed_at: float | None = None,
        success: bool = True,
    ) -> ObservedEffect:
        action = authorization["payload"]["action"]
        if action.get("action_type") != "mcp.tool.call":
            raise ValueError("MCP verifier requires action_type=mcp.tool.call")
        if action.get("target") != tool_name:
            raise ValueError("observed tool does not match authorized target")
        observation = {
            "tool_name": tool_name,
            "target_identity": target_identity,
            "result_sha256": digest(result),
        }
        return self.observe(
            authorization,
            observation=observation,
            evidence_ref=evidence_ref,
            result=result,
            status="SUCCEEDED" if success else "FAILED",
            observed_at=observed_at,
        )


class CallableMCPVerifier(MCPToolVerifier):
    """Run a separately supplied observation function, then verify its result."""

    def verify_call(
        self,
        authorization: dict[str, Any],
        *,
        tool_name: str,
        invoke: Callable[[], Any],
        evidence_ref: str,
        target_identity: str | None = None,
        observed_at: float | None = None,
    ) -> ObservedEffect:
        result = invoke()
        return self.verify_result(
            authorization,
            tool_name=tool_name,
            result=result,
            evidence_ref=evidence_ref,
            target_identity=target_identity,
            observed_at=observed_at,
        )
