"""Shared graph and profile requirement helpers."""
from __future__ import annotations

from typing import Any

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
