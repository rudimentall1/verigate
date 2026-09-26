"""Canonical execution-path identity for Verigate authorization.

Execution-graph identity is an enforcement boundary, not a sandbox. The
default scope is direct: Verigate binds the adapter/handler that it invokes,
but cannot infer or confine arbitrary transitive effects performed inside a
trusted handler. A transitive claim therefore requires an adapter to expose
an explicit matching enforcement scope.
"""
from __future__ import annotations
import hashlib, json
from typing import Any

_VALID_SCOPES = {"direct", "transitive"}

def normalize_execution_graph(graph: dict[str, Any] | None) -> dict[str, Any]:
    if graph is None: return {}
    if not isinstance(graph, dict): raise ValueError("execution graph must be an object")
    if not graph: return {}
    normalized = {str(k): graph[k] for k in sorted(graph)}
    scope = normalized.get("enforcement_scope", "direct")
    if scope not in _VALID_SCOPES:
        raise ValueError(f"unsupported execution enforcement scope: {scope}")
    normalized["enforcement_scope"] = scope
    return normalized

def execution_graph_digest(graph: dict[str, Any] | None) -> str:
    canonical=json.dumps(normalize_execution_graph(graph), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()

def verify_execution_graph(expected: dict[str, Any], actual: dict[str, Any]) -> tuple[bool, str]:
    expected, actual = normalize_execution_graph(expected), normalize_execution_graph(actual)
    if expected.get("enforcement_scope") == "transitive" and actual.get("enforcement_scope") != "transitive":
        return False, "execution graph requires transitive enforcement but adapter provides direct-only enforcement"
    if expected != actual:
        for key in sorted(set(expected) | set(actual)):
            if expected.get(key) != actual.get(key): return False, f"execution graph drift: {key}"
        return False, "execution graph drift"
    return True, "execution graph matches authorization"
