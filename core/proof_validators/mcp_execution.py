"""MCP execution proof-profile semantics."""
from __future__ import annotations
from typing import Any
from core.proof_engine import digest
from .common import validate_requirements

def validate(payload: dict[str, Any], profile: str = "mcp_execution") -> tuple[bool, str]:
    spec, node_types, edges, error = validate_requirements(payload, profile)
    if error:
        return False, error
    by_type = {node_type: [n for n in payload.get("nodes", []) if n["type"] == node_type] for node_type in node_types}
    required = {name: items[0] for name, items in by_type.items() if name in spec["required_nodes"] and len(items) == 1}
    if len(required) != len(spec["required_nodes"]):
        return False, "MCP execution profile requires exactly one canonical execution node of each required type"
    intent = required["action_intent"]
    decision = required["decision"]
    execution = required["execution_authorization"]
    receipt = required["execution_receipt"]
    claim = required["outcome_claim"]
    attestation = required["outcome_attestation"]
    attestor = required["attestor_authority"]

    intent_data = intent["data"]
    action = intent_data
    if intent["id"] != payload["intent_id"] or intent_data.get("intent_id") != payload["intent_id"]:
        return False, "MCP action intent is not bound to manifest intent_id"
    if action.get("action_type") != "mcp.tool.call":
        return False, "MCP execution proof requires action_type=mcp.tool.call"
    if not action.get("target"):
        return False, "MCP execution proof requires an authorized MCP target"
    decision_data = decision["data"] if isinstance(decision["data"], dict) else {"decision": decision["data"]}
    if decision["id"] != intent["id"] or decision_data.get("decision") != "ALLOW":
        return False, "MCP execution proof requires an ALLOW decision bound to the canonical intent"

    execution_payload = execution["data"].get("payload", {})
    authorized_action = execution_payload.get("action")
    if execution["id"] != payload["authorization_id"]:
        return False, "MCP execution authorization is not bound to manifest authorization_id"
    if execution_payload.get("authorization_id") != execution["id"]:
        return False, "MCP execution authorization has inconsistent authorization_id"
    if execution_payload.get("intent_id") != intent["id"] or execution_payload.get("agent_id") != payload["agent_id"]:
        return False, "MCP execution authorization identity binding is inconsistent"
    if not isinstance(authorized_action, dict) or authorized_action != action:
        return False, "MCP execution authorization action does not exactly match the canonical intent"
    if execution_payload.get("action_sha256") != digest(authorized_action):
        return False, "MCP execution authorization action fingerprint is invalid"
    if execution_payload.get("action_sha256") != digest(action):
        return False, "MCP execution authorization is not bound to the canonical MCP action"

    receipt_payload = receipt["data"].get("payload", {})
    if receipt_payload.get("authorization_id") != execution["id"]:
        return False, "MCP execution receipt is not bound to the exact authorization"
    if receipt_payload.get("intent_id") != intent["id"] or receipt_payload.get("agent_id") != payload["agent_id"]:
        return False, "MCP execution receipt identity binding is inconsistent"
    if receipt_payload.get("action_sha256") != execution_payload.get("action_sha256"):
        return False, "MCP execution receipt action fingerprint is inconsistent"

    claim_data = claim["data"]
    if claim_data.get("authorization_id") != execution["id"] or claim_data.get("intent_id") != intent["id"]:
        return False, "MCP outcome claim is not bound to the exact authorization and intent"
    if claim_data.get("agent_id") != payload["agent_id"]:
        return False, "MCP outcome claim is not bound to manifest agent_id"
    if claim_data.get("action_sha256") != execution_payload.get("action_sha256"):
        return False, "MCP outcome claim action fingerprint is inconsistent"
    if claim_data.get("execution_receipt_sha256") != digest(receipt["data"]):
        return False, "MCP outcome claim is not bound to the exact execution receipt"
    if claim_data.get("evidence_kind") != "MCP_RESULT":
        return False, "MCP execution proof requires MCP_RESULT evidence"
    if not claim_data.get("evidence_ref") or not claim_data.get("result_sha256"):
        return False, "MCP execution proof requires MCP evidence reference and result digest"

    attestation_payload = attestation["data"].get("payload", {})
    if attestation_payload.get("attestor_id") != attestor["id"]:
        return False, "MCP outcome attestation is not bound to the registered attestor"
    if attestation_payload.get("attestor_type") != "EXTERNAL_VERIFIER":
        return False, "MCP execution proof requires an independently registered external verifier"
    if attestor["data"].get("attestor_type") != "EXTERNAL_VERIFIER":
        return False, "MCP execution proof attestor authority is not an external verifier"
    if attestation_payload.get("claim", {}).get("claim_id") != claim["id"]:
        return False, "MCP outcome attestation is not bound to the canonical outcome claim"
    if attestation_payload.get("claim_sha256") != digest(claim["data"]):
        return False, "MCP outcome attestation claim fingerprint is inconsistent"

    if not any(
        edge.get("from") == f"action_intent:{intent['id']}"
        and edge.get("relation") == "EVALUATED_AS"
        and edge.get("to") == f"decision:{decision['id']}"
        for edge in edges
    ):
        return False, "MCP execution proof is missing canonical intent evaluation provenance"
    if not any(
        edge.get("from") == f"decision:{decision['id']}"
        and edge.get("relation") == "MINTS"
        and edge.get("to") == f"execution_authorization:{execution['id']}"
        for edge in edges
    ):
        return False, "MCP execution proof is missing decision-to-authorization provenance"
    return True, "MCP execution proof profile satisfied"
