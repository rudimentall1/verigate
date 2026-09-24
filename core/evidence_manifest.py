"""Portable, signed Evidence Manifest and offline verification.

The manifest is a deterministic export of the authority lifecycle for one
consequential action. It is deliberately independent of SQLite and the API so
an auditor can verify integrity without access to Verigate itself.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _node_leaf(node: dict[str, Any]) -> str:
    return hashlib.sha256(("node:" + node["sha256"]).encode("ascii")).hexdigest()


def _edge_leaf(edge: dict[str, str]) -> str:
    return hashlib.sha256(("edge:" + digest(edge)).encode("ascii")).hexdigest()


def merkle_root(leaves: list[str]) -> str:
    if not leaves:
        return hashlib.sha256(b"VERIGATE-EVIDENCE-MERKLE:v1:empty").hexdigest()
    level = sorted(leaves)
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [
            hashlib.sha256(("pair:" + level[i] + ":" + level[i + 1]).encode("ascii")).hexdigest()
            for i in range(0, len(level), 2)
        ]
    return level[0]


def graph_root(graph: dict[str, Any]) -> str:
    leaves = [_node_leaf(node) for node in graph.get("nodes", [])]
    leaves.extend(_edge_leaf(edge) for edge in graph.get("edges", []))
    return merkle_root(leaves)


def _manifest_payload(graph: dict[str, Any]) -> dict[str, Any]:
    return {
        "manifest_version": 1,
        "authorization_id": graph["authorization_id"],
        "intent_id": graph["intent_id"],
        "agent_id": graph["agent_id"],
        "graph_version": graph.get("graph_version", 1),
        "nodes": graph.get("nodes", []),
        "edges": graph.get("edges", []),
        "verification": graph.get("verification", {}),
        "audit": graph.get("audit", {}),
        "root_digest": graph_root(graph),
    }


def build_manifest(graph: dict[str, Any], private_key: Ed25519PrivateKey) -> dict[str, Any]:
    payload = _manifest_payload(graph)
    signature = base64.b64encode(private_key.sign(canonical(payload))).decode("ascii")
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "payload": payload,
        "signature": signature,
        "algorithm": "Ed25519",
        "issuer_public_key_b64": base64.b64encode(public_key).decode("ascii"),
    }


def _verify_nodes(payload: dict[str, Any]) -> tuple[bool, str]:
    nodes = payload.get("nodes")
    edges = payload.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return False, "manifest graph is malformed"
    node_refs: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict) or not all(k in node for k in ("type", "id", "sha256", "data")):
            return False, "manifest contains malformed node"
        if digest(node["data"]) != node["sha256"]:
            return False, f"node digest mismatch: {node.get('type')}:{node.get('id')}"
        ref = f"{node['type']}:{node['id']}"
        if ref in node_refs:
            return False, f"duplicate node: {ref}"
        node_refs.add(ref)
    for edge in edges:
        if not isinstance(edge, dict) or not all(k in edge for k in ("from", "relation", "to")):
            return False, "manifest contains malformed edge"
        if edge["from"] not in node_refs or edge["to"] not in node_refs:
            return False, "manifest contains dangling edge"
    return True, "all graph nodes and edges are internally consistent"


def verify_manifest(
    manifest: dict[str, Any],
    trusted_public_key_b64: str | None = None,
) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        return {"valid": False, "reason": "manifest must be an object"}
    payload = manifest.get("payload")
    signature = manifest.get("signature")
    embedded = manifest.get("issuer_public_key_b64")
    if not isinstance(payload, dict) or not isinstance(signature, str) or not isinstance(embedded, str):
        return {"valid": False, "reason": "manifest envelope is incomplete"}
    if payload.get("manifest_version") != 1:
        return {"valid": False, "reason": "unsupported manifest version"}
    graph_ok, graph_reason = _verify_nodes(payload)
    if not graph_ok:
        return {"valid": False, "reason": graph_reason}
    expected_root = graph_root(payload)
    if payload.get("root_digest") != expected_root:
        return {"valid": False, "reason": "evidence Merkle root mismatch"}
    try:
        raw = base64.b64decode(embedded, validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError, TypeError):
        return {"valid": False, "reason": "invalid embedded issuer public key"}
    if trusted_public_key_b64 is not None:
        if trusted_public_key_b64 != embedded:
            return {"valid": False, "reason": "issuer public key is not trusted"}
    try:
        public_key.verify(base64.b64decode(signature, validate=True), canonical(payload))
    except (InvalidSignature, ValueError, TypeError):
        return {"valid": False, "reason": "invalid manifest signature"}
    verification = payload.get("verification") or {}
    invalid_evidence = [
        key for key, item in verification.items()
        if isinstance(item, dict) and item.get("valid") is False
    ]
    if invalid_evidence:
        return {
            "valid": False,
            "reason": "evidence verification failed",
            "invalid_evidence": invalid_evidence,
            "root_digest": expected_root,
        }
    return {
        "valid": True,
        "reason": "valid signed evidence manifest",
        "root_digest": expected_root,
        "node_count": len(payload["nodes"]),
        "edge_count": len(payload["edges"]),
        "embedded_issuer_trusted": trusted_public_key_b64 is not None,
        "invalid_evidence": invalid_evidence,
    }
