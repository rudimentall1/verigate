"""Shared graph and profile requirement helpers."""
from __future__ import annotations

from typing import Any
import hashlib
import json

from core.proof_profiles import profile_spec


def validate_requirements(
    payload: dict[str, Any], profile: str
) -> tuple[dict[str, Any] | None, set[str], list[dict[str, Any]], str | None]:
    spec = profile_spec(profile)
    if spec is None:
        return None, set(), [], f"unsupported proof profile: {profile}"

    node_types = {node["type"] for node in payload.get("nodes", [])}
    missing_nodes = sorted(spec["required_nodes"] - node_types)
    if missing_nodes:
        return spec, node_types, [], "proof profile missing required nodes: " + ", ".join(missing_nodes)

    edges = payload.get("edges", [])
    edge_pairs = {
        (edge["from"].split(":", 1)[0], edge["relation"], edge["to"].split(":", 1)[0])
        for edge in edges
    }
    missing_edges = sorted(spec["required_edges"] - edge_pairs)
    if missing_edges:
        return spec, node_types, edges, "proof profile missing required relations: " + ", ".join(
            f"{source}->{relation}->{target}" for source, relation, target in missing_edges
        )
    return spec, node_types, edges, None


def intent_context_digest(intent: dict[str, Any]) -> str:
    payload = {
        "purpose": intent.get("purpose", ""),
        "declared_context": intent.get("declared_context", {}),
        "input_provenance": intent.get("input_provenance", {}),
        "parent_intent_id": intent.get("parent_intent_id"),
        "requested_capability": intent.get("requested_capability"),
        "constraints": intent.get("constraints", {}),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_context_binding(intent: dict[str, Any], decision: dict[str, Any]) -> tuple[bool, str]:
    expected = intent_context_digest(intent)
    actual = decision.get("context_sha256")
    if actual != expected:
        return False, "decision is not cryptographically bound to the canonical intent context"
    return True, "intent context binding is valid"


def validate_execution_enforcement_scope(
    execution_payload: dict[str, Any],
) -> tuple[bool, str]:
    """Validate only execution scopes that the proof protocol can independently establish.

    Genesis 2.0 currently proves the direct execution boundary. A transitive
    scope would require independent evidence that delegated child effects were
    themselves constrained; a signed claim inside the authorization is not
    sufficient evidence for an offline verifier.
    """
    graph = execution_payload.get("execution_graph")
    if not isinstance(graph, dict):
        return False, "execution authorization is missing execution graph binding"
    scope = graph.get("enforcement_scope", "direct") if graph else "direct"
    if scope == "direct":
        return True, "direct execution enforcement scope is valid"
    if scope == "transitive":
        return False, "transitive execution enforcement is not independently provable by authority-proof-v1"
    return False, f"unsupported execution enforcement scope: {scope}"
