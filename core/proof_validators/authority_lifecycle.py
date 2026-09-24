"""Authority lifecycle proof-profile semantics."""
from __future__ import annotations
from typing import Any
from core.proof_engine import digest
from .common import validate_requirements

def validate(payload: dict[str, Any], profile: str = "authority_lifecycle") -> tuple[bool, str]:
    spec, node_types, edges, error = validate_requirements(payload, profile)
    if error:
        return False, error
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
