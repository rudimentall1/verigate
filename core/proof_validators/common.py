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


def validate_external_state_execution_scope(
    execution_payload: dict[str, Any],
    execution_receipt_payload: dict[str, Any],
) -> tuple[bool, str]:
    """Validate the execution contract recorded for policy-required external state.

    The proof verifies the signed adapter contract and exact state binding. It
    does not claim to sandbox arbitrary generic adapter internals; "atomic"
    remains an explicit trusted-adapter boundary. EVM adapters additionally
    enforce the committed guard on-chain.
    """
    required = bool(execution_payload.get("external_state_required"))
    scope = execution_receipt_payload.get("execution_external_state_scope")
    external_state = execution_payload.get("external_state")
    requirement = execution_payload.get("external_state_requirement")

    if not required:
        if scope not in (None, "atomic"):
            return False, f"unsupported execution external-state scope: {scope}"
        return True, "external state execution is not required"

    if scope != "atomic":
        return False, "required external state execution is not atomically enforced"
    if not isinstance(external_state, dict) or not external_state:
        return False, "required external state binding is missing"
    if not isinstance(requirement, dict):
        return False, "required external state policy requirement is missing"

    state_json = json.dumps(
        external_state, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    requirement_json = json.dumps(
        requirement, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    if execution_payload.get("external_state_sha256") != hashlib.sha256(state_json).hexdigest():
        return False, "external state fingerprint mismatch"
    if execution_payload.get("external_state_requirement_sha256") != hashlib.sha256(requirement_json).hexdigest():
        return False, "external state requirement fingerprint mismatch"
    if external_state.get("kind") != requirement.get("kind"):
        return False, "external state kind does not satisfy policy requirement"
    reference = external_state.get("reference")
    if not isinstance(reference, str) or not reference.strip():
        return False, "external state binding is missing reference"
    digest_value = external_state.get("digest")
    if not isinstance(digest_value, str) or len(digest_value) != 64:
        return False, "external state binding has invalid digest"
    try:
        int(digest_value, 16)
    except ValueError:
        return False, "external state binding digest is not hexadecimal"
    return True, "required external state execution is atomically bound"
