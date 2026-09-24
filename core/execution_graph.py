"""Canonical execution-path identity for Verigate authorization."""
from __future__ import annotations
import hashlib, json
from typing import Any

def normalize_execution_graph(graph: dict[str, Any] | None) -> dict[str, Any]:
    if graph is None: return {}
    if not isinstance(graph, dict): raise ValueError("execution graph must be an object")
    return {str(k): graph[k] for k in sorted(graph)}

def execution_graph_digest(graph: dict[str, Any] | None) -> str:
    canonical=json.dumps(normalize_execution_graph(graph), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()

def verify_execution_graph(expected: dict[str, Any], actual: dict[str, Any]) -> tuple[bool, str]:
    expected, actual = normalize_execution_graph(expected), normalize_execution_graph(actual)
    if expected != actual:
        for key in sorted(set(expected) | set(actual)):
            if expected.get(key) != actual.get(key): return False, f"execution graph drift: {key}"
        return False, "execution graph drift"
    return True, "execution graph matches authorization"
