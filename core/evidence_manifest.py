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

from core.proof_profiles import PROOF_PROFILES, assurance_claims, profile_spec


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


def _validate_profile(payload: dict[str, Any], profile: str) -> tuple[bool, str]:
    spec = profile_spec(profile)
    if spec is None:
        return False, f"unsupported proof profile: {profile}"
    node_types = {node["type"] for node in payload.get("nodes", [])}
    missing_nodes = sorted(spec["required_nodes"] - node_types)
    if missing_nodes:
        return False, "proof profile missing required nodes: " + ", ".join(missing_nodes)
    edges = payload.get("edges", [])
    edge_pairs = {
        (edge["from"].split(":", 1)[0], edge["relation"], edge["to"].split(":", 1)[0])
        for edge in edges
    }
    missing_edges = sorted(spec["required_edges"] - edge_pairs)
    if missing_edges:
        return False, "proof profile missing required relations: " + ", ".join(
            f"{source}->{relation}->{target}" for source, relation, target in missing_edges
        )
    if profile == "mcp_execution":
        by_type = {node_type: [n for n in payload.get("nodes", []) if n["type"] == node_type] for node_type in node_types}
        required = {name: items[0] for name, items in by_type.items() if name in spec["required_nodes"] and len(items) == 1}
        if len(required) != len(spec["required_nodes"]):
            return False, "MCP execution profile requires exactly one canonical execution node of each required type"
        intent = required["action_intent"]
        execution = required["execution_authorization"]
        receipt = required["execution_receipt"]
        claim = required["outcome_claim"]
        attestation = required["outcome_attestation"]
        attestor = required["attestor_authority"]
        action = intent["data"].get("action", {})
        if action.get("action_type") != "mcp.tool.call":
            return False, "MCP execution proof requires action_type=mcp.tool.call"
        target = action.get("target")
        if not target:
            return False, "MCP execution proof requires an authorized MCP target"
        execution_payload = execution["data"].get("payload", {})
        if execution_payload.get("intent_id") != intent["id"]:
            return False, "MCP execution authorization is not bound to the canonical intent"
        receipt_payload = receipt["data"].get("payload", {})
        if receipt_payload.get("authorization_id") != execution["id"] or receipt_payload.get("action_sha256") != execution_payload.get("action_sha256"):
            return False, "MCP execution receipt is not bound to the exact authorization"
        if claim["data"].get("execution_receipt_sha256") != digest(receipt["data"]):
            return False, "MCP outcome claim is not bound to the exact execution receipt"
        if claim["data"].get("evidence_kind") != "MCP_RESULT":
            return False, "MCP execution proof requires MCP_RESULT evidence"
        if attestation["data"].get("attestor_id") != attestor["id"]:
            return False, "MCP outcome attestation is not bound to the registered attestor"
        if not any(edge.get("from") == f"action_intent:{intent['id']}" and edge.get("relation") == "EVALUATED_AS" for edge in edges):
            return False, "MCP execution proof is missing intent evaluation provenance"
        return True, "MCP execution proof profile satisfied"
    if profile != "authority_lifecycle":
        return True, "proof profile satisfied"

    by_type = {node_type: [n for n in payload.get("nodes", []) if n["type"] == node_type] for node_type in node_types}

    def one(node_type: str) -> dict[str, Any] | None:
        items = by_type.get(node_type, [])
        return items[0] if len(items) == 1 else None

    required = {name: one(name) for name in spec["required_nodes"]}
    if any(value is None for value in required.values()):
        return False, "authority lifecycle profile requires exactly one canonical node of each required type"

    verification = payload.get("verification")
    if not isinstance(verification, dict) or verification.get("all_signed_artifacts_valid") is not True:
        return False, "authority lifecycle proof requires all signed artifacts to be independently verified"
    invalid_evidence = [
        key for key, item in verification.items()
        if isinstance(item, dict) and item.get("valid") is False
    ]
    if invalid_evidence:
        return False, "authority lifecycle proof contains invalid signed evidence: " + ", ".join(sorted(invalid_evidence))

    intent = required["action_intent"]
    decision = required["decision"]
    decision_receipt = required["decision_receipt"]
    policy = required["policy_version"]
    execution = required["execution_authorization"]
    receipt = required["execution_receipt"]
    claim = required["outcome_claim"]
    attestation = required["outcome_attestation"]
    identity = required["identity"]
    capability = required["capability"]
    attestor = required["attestor_authority"]
    authority_event = required["authority_event"]

    if intent["id"] != payload["intent_id"] or intent["data"].get("intent_id") != payload["intent_id"]:
        return False, "action intent is not bound to manifest intent_id"
    decision_data = decision["data"] if isinstance(decision["data"], dict) else {"decision": decision["data"]}
    receipt_payload = decision_receipt["data"].get("payload", {})
    receipt_intent = receipt_payload.get("intent", {})
    receipt_decision = receipt_payload.get("decision", {})
    if decision["id"] != intent["id"] or decision_data.get("decision") != "ALLOW":
        return False, "authority lifecycle proof requires an ALLOW decision bound to the canonical intent"
    if receipt_intent.get("intent_id") != intent["id"] or receipt_decision.get("intent_id") != intent["id"]:
        return False, "decision receipt is not bound to the canonical intent"
    if receipt_decision.get("decision") != decision_data.get("decision"):
        return False, "decision receipt is not bound to the canonical decision"
    if receipt_payload.get("policy_sha256") != policy["id"]:
        return False, "policy version is not the policy used by the decision"

    execution_payload = execution["data"].get("payload", {})
    if execution["id"] != payload["authorization_id"] or execution_payload.get("authorization_id") != execution["id"]:
        return False, "execution authorization is not bound to manifest authorization_id"
    if execution_payload.get("intent_id") != intent["id"] or execution_payload.get("agent_id") != payload["agent_id"]:
        return False, "execution authorization identity binding is inconsistent"

    execution_receipt_payload = receipt["data"].get("payload", {})
    if execution_receipt_payload.get("authorization_id") != execution["id"] or execution_receipt_payload.get("intent_id") != intent["id"]:
        return False, "execution receipt is not bound to the execution authorization"
    if execution_receipt_payload.get("agent_id") != payload["agent_id"]:
        return False, "execution receipt is not bound to manifest agent_id"

    claim_data = claim["data"]
    if claim_data.get("authorization_id") != execution["id"] or claim_data.get("intent_id") != intent["id"]:
        return False, "outcome claim is not bound to the execution authorization"
    if claim_data.get("agent_id") != payload["agent_id"]:
        return False, "outcome claim is not bound to manifest agent_id"
    if claim_data.get("execution_receipt_sha256") != digest(receipt["data"]):
        return False, "outcome claim is not bound to the execution receipt"

    attestation_payload = attestation["data"].get("payload", {})
    attested_claim = attestation_payload.get("claim", {})
    if attested_claim.get("claim_id") != claim["id"] or attestation_payload.get("claim_sha256") != digest(claim["data"]):
        return False, "outcome attestation is not bound to the canonical outcome claim"
    if attested_claim.get("authorization_id") != execution["id"]:
        return False, "outcome attestation authorization binding is inconsistent"
    if attestor["id"] != attestation_payload.get("attestor_id") or attestor["data"].get("attestor_id") != attestor["id"]:
        return False, "outcome attestation is not bound to the registered attestor"

    if identity["id"] != execution_payload.get("identity_id") or identity["data"].get("agent_id") != payload["agent_id"]:
        return False, "identity binding is inconsistent with execution authorization"
    if capability["id"] != execution_payload.get("capability_id") or capability["data"].get("agent_id") != payload["agent_id"]:
        return False, "capability binding is inconsistent with execution authorization"
    if authority_event["data"].get("evidence_ref") != claim["id"]:
        return False, "authority event is not informed by the canonical outcome claim"
    if authority_event["data"].get("agent_id") != payload["agent_id"] or authority_event["data"].get("capability_id") != capability["id"]:
        return False, "authority event identity binding is inconsistent"

    def has_edge(source_type: str, source_id: str, relation: str, target_type: str, target_id: str) -> bool:
        return any(
            edge.get("from") == f"{source_type}:{source_id}"
            and edge.get("relation") == relation
            and edge.get("to") == f"{target_type}:{target_id}"
            for edge in edges
        )

    exact_edges = [
        ("identity", identity["id"], "AUTHENTICATES", "action_intent", intent["id"]),
        ("capability", capability["id"], "AUTHORIZES", "action_intent", intent["id"]),
        ("decision", decision["id"], "MINTS", "execution_authorization", execution["id"]),
        ("execution_authorization", execution["id"], "PRODUCES", "execution_receipt", receipt["id"]),
        ("execution_receipt", receipt["id"], "OBSERVED_BY", "outcome_claim", claim["id"]),
        ("outcome_attestation", attestation["id"], "ATTESTS", "outcome_claim", claim["id"]),
        ("attestor_authority", attestor["id"], "AUTHORIZES", "outcome_attestation", attestation["id"]),
        ("outcome_claim", claim["id"], "INFORMS", "authority_event", authority_event["id"]),
    ]
    for source_type, source_id, relation, target_type, target_id in exact_edges:
        if not has_edge(source_type, source_id, relation, target_type, target_id):
            return False, f"authority lifecycle relation is not bound to canonical nodes: {source_type}:{source_id}->{relation}->{target_type}:{target_id}"

    governed_actions = [
        node for node in payload.get("nodes", [])
        if node["type"] == "governance_action"
        and node["data"].get("attestor_id") == attestor["id"]
        and has_edge("attestor_authority", attestor["id"], "DERIVED_FROM", "governance_action", node["id"])
    ]
    if not governed_actions:
        return False, "attestor authority has no matching governed registration lineage"
    action_ids = {node["id"] for node in governed_actions}
    approval_edges = [
        edge for edge in edges
        if edge.get("relation") == "APPROVES"
        and edge.get("to") in {f"governance_action:{action_id}" for action_id in action_ids}
    ]
    if not approval_edges:
        return False, "governed attestor action has no linked governance approval"
    nodes_by_ref = {f"{node['type']}:{node['id']}": node for node in payload.get("nodes", [])}
    for edge in approval_edges:
        approval = nodes_by_ref.get(edge.get("from"))
        action = nodes_by_ref.get(edge.get("to"))
        if approval is None or action is None:
            return False, "governance approval lineage references missing canonical nodes"
        approval_payload = approval["data"].get("payload", {})
        if approval_payload.get("action_digest") != digest(action["data"]):
            return False, "governance approval is not bound to the approved governance action"

    return True, "authority lifecycle proof profile satisfied"


def _manifest_payload(graph: dict[str, Any], proof_profile: str = "integrity") -> dict[str, Any]:
    return {
        "manifest_version": 1,
        "proof_profile": proof_profile,
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


def build_manifest(
    graph: dict[str, Any],
    private_key: Ed25519PrivateKey,
    proof_profile: str = "integrity",
) -> dict[str, Any]:
    payload = _manifest_payload(graph, proof_profile)
    profile_ok, profile_reason = _validate_profile(payload, proof_profile)
    if not profile_ok:
        raise ValueError(profile_reason)
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
    proof_profile = payload.get("proof_profile", "integrity")
    graph_ok, graph_reason = _verify_nodes(payload)
    if not graph_ok:
        return {"valid": False, "reason": graph_reason}
    profile_ok, profile_reason = _validate_profile(payload, proof_profile)
    if not profile_ok:
        return {"valid": False, "reason": profile_reason, "proof_profile": proof_profile}
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
        "assurance": {
            "profile": proof_profile,
            "claims": assurance_claims(proof_profile),
        },
    }
