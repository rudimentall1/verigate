"""Authority lifecycle proof-profile semantics."""
from __future__ import annotationsimport math
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.proof_engine import canonical, digest
from core.authority_protocol import Authority, AuthorityState as GenesisAuthorityState
from core.governance import GovernancePolicy, verify_governance_quorum
from core.attestor_history import (
    replay_attestor_governance_state as _replay_attestor_governance_state,
    verify_outcome_attestation_signature as _verify_outcome_attestation_signature,
)
from .common import (
    validate_requirements,
    validate_context_binding,
    validate_execution_enforcement_scope,
    validate_external_state_execution_scope,
    validate_observed_effect_binding,
    validate_authority_learning_binding,
    validate_historical_authority_binding,
)

def validate(payload: dict[str, Any], profile: str = "authority_lifecycle") -> tuple[bool, str]:
    spec, node_types, edges, error = validate_requirements(payload, profile)
    if error:
        return False, error
    by_type = {node_type: [n for n in payload.get("nodes", []) if n["type"] == node_type] for node_type in node_types}

    def one(node_type: str) -> dict[str, Any] | None:
        items = by_type.get(node_type, [])
        return items[0] if len(items) == 1 else None

    # Governance actions and approvals form an ordered, repeatable history;
    # every other protocol artifact is a singleton canonical node.
    repeatable_history_types = {"governance_action", "governance_approval"}
    required = {
        name: one(name)
        for name in spec["required_nodes"]
        if name not in repeatable_history_types
    }
    if any(value is None for value in required.values()):
        return False, "authority lifecycle profile requires exactly one canonical node of each singleton type"
    if any(not by_type.get(name) for name in repeatable_history_types):
        return False, "authority lifecycle profile requires governance action and approval history"

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
    authority_state = required["authority_state"]
    genesis = required["genesis_authority"]
    execution = required["execution_authorization"]
    receipt = required["execution_receipt"]
    claim = required["outcome_claim"]
    observed_effect = required["observed_effect"]
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

    context_ok, context_reason = validate_context_binding(intent["data"], decision_data)
    if not context_ok:
        return False, context_reason
    if receipt_intent.get("intent_id") != intent["id"] or receipt_decision.get("intent_id") != intent["id"]:
        return False, "decision receipt is not bound to the canonical intent"
    if receipt_decision.get("decision") != decision_data.get("decision"):
        return False, "decision receipt is not bound to the canonical decision"
    if receipt_intent != intent["data"]:
        return False, "decision receipt intent payload differs from the canonical intent"
    if receipt_payload.get("policy_sha256") != policy["id"]:
        return False, "policy version is not the policy used by the decision"

    execution_payload = execution["data"].get("payload", {})
    if execution["id"] != payload["authorization_id"] or execution_payload.get("authorization_id") != execution["id"]:
        return False, "execution authorization is not bound to manifest authorization_id"
    if execution_payload.get("intent_id") != intent["id"] or execution_payload.get("agent_id") != payload["agent_id"]:
        return False, "execution authorization identity binding is inconsistent"
    if execution_payload.get("action") != intent["data"]:
        return False, "execution authorization action payload differs from the canonical intent"
    scope_ok, scope_reason = validate_execution_enforcement_scope(execution_payload)
    if not scope_ok:
        return False, scope_reason

    if execution_payload.get("capability_id") != capability["id"]:
        return False, "execution authorization capability binding is inconsistent"
    if execution_payload.get("identity_id") != identity["id"]:
        return False, "execution authorization identity binding is inconsistent"
    if execution_payload.get("capability_sha256") != capability["data"].get("digest"):
        return False, "execution authorization capability digest is not bound to the canonical capability"
    if execution_payload.get("identity_sha256") != identity["data"].get("identity_sha256"):
        return False, "execution authorization identity digest is not bound to the canonical identity"

    state_data = authority_state["data"]
    if execution_payload.get("authority_state_sha256") != digest(state_data):
        return False, "execution authorization authority state is not bound to the canonical snapshot"
    if execution_payload.get("authority_state") != state_data:
        return False, "execution authorization authority state payload differs from the canonical snapshot"

    ledger_node_for_history = one("authority_ledger")
    if ledger_node_for_history is None:
        return False, "authority ledger evidence is missing"
    historical_ok, historical_reason = validate_historical_authority_binding(
        state_data,
        ledger_node_for_history["data"].get("entries", []),
        execution_payload.get("authority_policy") or {},
        execution_payload.get("authority_ledger_head_hash", ""),
    )
    if not historical_ok:
        return False, historical_reason

    genesis_data = genesis["data"]
    if execution_payload.get("genesis_authority") != genesis_data:
        return False, "execution authorization Genesis authority provenance differs from the canonical evidence"
    if execution_payload.get("genesis_authority_sha256") != digest(genesis_data):
        return False, "execution authorization Genesis authority fingerprint mismatch"
    if genesis_data.get("protocol") != "genesis-2.0":
        return False, "unsupported Genesis authority protocol"
    try:
        reconstructed_authority = Authority(
            authority_id=f"{payload['agent_id']}:{capability['id']}:{state_data.get('ledger_head_hash') or digest(state_data)}",
            agent_id=payload["agent_id"],
            identity_id=identity["id"],
            capability_id=capability["id"],
            capability_version=capability["data"].get("version", 1),
            capability_sha256=execution_payload.get("capability_sha256", ""),
            state=GenesisAuthorityState(state_data["state"]),
            multiplier=float(state_data["multiplier"]),
            ledger_head_hash=state_data.get("ledger_head_hash", ""),
            effective_from=float(state_data.get("evaluated_at", 0.0)),
            metadata={
                "source": "core.authority_state.AuthoritySnapshot",
                "successes": state_data.get("successes", 0),
                "adverse_events": state_data.get("adverse_events", 0),
                "critical_events": state_data.get("critical_events", 0),
                "reason": state_data.get("reason", ""),
            },
        )
    except (KeyError, TypeError, ValueError):
        return False, "historical authority snapshot cannot reconstruct Genesis authority"
    if genesis_data.get("authority_digest") != reconstructed_authority.digest:
        return False, "Genesis authority is not bound to the historical authority snapshot"
    if genesis_data.get("capability_digest") != execution_payload.get("capability_sha256"):
        return False, "Genesis authority is not bound to the execution capability"

    execution_receipt_payload = receipt["data"].get("payload", {})
    if execution_receipt_payload.get("authorization_id") != execution["id"] or execution_receipt_payload.get("intent_id") != intent["id"]:
        return False, "execution receipt is not bound to the execution authorization"
    if execution_receipt_payload.get("authorization_sha256") != digest(execution_payload):
        return False, "execution receipt is not bound to the exact execution authorization payload"
    if execution_receipt_payload.get("agent_id") != payload["agent_id"]:
        return False, "execution receipt is not bound to manifest agent_id"
    external_scope_ok, external_scope_reason = validate_external_state_execution_scope(
        execution_payload,
        execution_receipt_payload,
    )
    if not external_scope_ok:
        return False, external_scope_reason

    claim_data = claim["data"]
    if claim_data.get("authorization_id") != execution["id"] or claim_data.get("intent_id") != intent["id"]:
        return False, "outcome claim is not bound to the execution authorization"
    if claim_data.get("agent_id") != payload["agent_id"]:
        return False, "outcome claim is not bound to manifest agent_id"
    if claim_data.get("execution_receipt_sha256") != digest(receipt["data"]):
        return False, "outcome claim is not bound to the execution receipt"
    observed_ok, observed_reason = validate_observed_effect_binding(
        claim_data,
        observed_effect["data"],
        require_observation=True,
    )
    if not observed_ok:
        return False, observed_reason
    if observed_effect["id"] != claim_data.get("observed_effect_sha256"):
        return False, "observed-effect node is not bound to the claim fingerprint"

    attestation_payload = attestation["data"].get("payload", {})
    attested_claim = attestation_payload.get("claim", {})
    if attested_claim != claim["data"]:
        return False, "outcome attestation claim payload differs from the canonical outcome claim"
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
    authority_state_after_ledger = []
    for node in payload.get("nodes", []):
        if node.get("type") == "authority_ledger":
            authority_state_after_ledger = node.get("data", {}).get("entries", [])
            break
    learning_ok, learning_reason = validate_authority_learning_binding(
        claim_data,
        attestation_payload,
        authority_event["data"],
        state_data,
        required["authority_state_after"]["data"],
        authority_state_after_ledger,
        execution_payload.get("authority_policy") or {},
        execution_payload.get("authority_ledger_head_hash", ""),
    )
    if not learning_ok:
        return False, learning_reason

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
        ("genesis_authority", genesis["id"], "JUSTIFIES", "execution_authorization", execution["id"]),
        ("execution_authorization", execution["id"], "PRODUCES", "execution_receipt", receipt["id"]),
        ("execution_receipt", receipt["id"], "OBSERVED_BY", "outcome_claim", claim["id"]),
        ("outcome_claim", claim["id"], "SUPPORTED_BY", "observed_effect", observed_effect["id"]),
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

    nodes_by_ref = {
        f"{node['type']}:{node['id']}": node
        for node in payload.get("nodes", [])
    }
    verified_governance_actions: list[tuple[float, dict[str, Any]]] = []
    for action_node in governed_actions:
        action_id = action_node["id"]
        action_data = action_node["data"]
        action_ref = f"governance_action:{action_id}"
        if not isinstance(action_data, dict) or action_data.get("action_id") != action_id:
            return False, "governance action identifier does not match its evidence node"
        if action_data.get("attestor_id") != attestor["id"]:
            return False, "governance action targets a different attestor"
        if action_data.get("action") not in {
            "ATTESTOR_REGISTER",
            "ATTESTOR_ACTIVATE",
            "ATTESTOR_ROTATE",
            "ATTESTOR_REVOKE",
            "ATTESTOR_EXPIRE",
        }:
            return False, "unsupported attestor governance action"

        policy_edges = [
            edge for edge in edges
            if edge.get("relation") == "GOVERNS"
            and edge.get("to") == action_ref
        ]
        if len(policy_edges) != 1:
            return False, "governance action must have exactly one linked governance policy"
        policy_node = nodes_by_ref.get(policy_edges[0].get("from"))
        if policy_node is None or policy_node.get("type") != "governance_policy":
            return False, "governance action references missing governance policy evidence"
        policy_data = policy_node.get("data")
        if not isinstance(policy_data, dict):
            return False, "governance policy evidence is malformed"

        approval_edges = [
            edge for edge in edges
            if edge.get("relation") == "APPROVES"
            and edge.get("to") == action_ref
        ]
        if not approval_edges:
            return False, "governed attestor action has no linked governance approval"

        approval_data = []
        approval_ids = set()
        approval_issue_times = []
        for edge in approval_edges:
            approval_node = nodes_by_ref.get(edge.get("from"))
            if approval_node is None or approval_node.get("type") != "governance_approval":
                return False, "governance approval lineage references missing canonical nodes"
            approval_id = approval_node.get("id")
            signed_approval = approval_node.get("data")
            approval_payload = signed_approval.get("payload") if isinstance(signed_approval, dict) else None
            if (
                not isinstance(approval_payload, dict)
                or approval_payload.get("approval_id") != approval_id
                or approval_id in approval_ids
            ):
                return False, "governance approval identity is missing, duplicated, or inconsistent"
            issued_at = approval_payload.get("issued_at")
            if (
                isinstance(issued_at, bool)
                or not isinstance(issued_at, (int, float))
                or not math.isfinite(float(issued_at))
            ):
                return False, "governance approval issue time is invalid"
            approval_issue_times.append(float(issued_at))
            approval_ids.add(approval_id)
            approval_data.append(signed_approval)

        action_issued_at = action_data.get("issued_at")
        if (
            isinstance(action_issued_at, bool)
            or not isinstance(action_issued_at, (int, float))
            or not math.isfinite(float(action_issued_at))
        ):
            return False, "governance action issue time is invalid"
        # Verify the quorum at the first instant all collected signatures
        # existed. This keeps an expired historical approval verifiable while
        # still requiring every signature and the action to have been live.
        verification_time = max(
            [float(action_issued_at), *approval_issue_times]
        )
        try:
            policy = GovernancePolicy.from_dict(policy_data)
            if policy.digest != action_data.get("governance_policy_sha256"):
                return False, "governance action policy fingerprint does not match policy evidence"
            valid_quorum, quorum_reason = verify_governance_quorum(
                action_data,
                approval_data,
                policy,
                now=verification_time,
            )
        except (TypeError, ValueError, KeyError) as exc:
            return False, f"invalid governance quorum evidence: {exc}"
        if not valid_quorum:
            return False, f"governance quorum verification failed: {quorum_reason}"
        verified_governance_actions.append((verification_time, action_data))

    attestation_payload = attestation["data"].get("payload", {})
    attested_at = attestation_payload.get("attested_at")
    if (
        isinstance(attested_at, bool)
        or not isinstance(attested_at, (int, float))
        or not math.isfinite(float(attested_at))
    ):
        return False, "outcome attestation timestamp is invalid"
    governance_state_ok, governance_state_reason, historical_attestor = (
        _replay_attestor_governance_state(
            verified_governance_actions,
            attestor["data"],
            float(attested_at),
        )
    )
    if not governance_state_ok or historical_attestor is None:
        return False, governance_state_reason
    attestation_signature_ok, attestation_signature_reason = _verify_outcome_attestation_signature(
        attestation["data"],
        historical_attestor,
    )
    if not attestation_signature_ok:
        return False, attestation_signature_reason

    return True, "authority lifecycle proof profile satisfied"
