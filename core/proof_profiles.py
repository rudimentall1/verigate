"""Declarative proof-profile registry for portable Verigate evidence."""
from __future__ import annotations
from typing import Any

PROOF_PROFILES: dict[str, dict[str, Any]] = {
    "integrity": {
        "required_nodes": set(),
        "required_edges": set(),
        "assurance_claims": ["signed_manifest", "graph_integrity"],
    },
    "mcp_execution": {
        "required_nodes": {
            "action_intent", "execution_authorization", "execution_receipt",
            "outcome_claim", "outcome_attestation", "attestor_authority",
        },
        "required_edges": {
            ("execution_authorization", "PRODUCES", "execution_receipt"),
            ("execution_receipt", "OBSERVED_BY", "outcome_claim"),
            ("outcome_attestation", "ATTESTS", "outcome_claim"),
            ("attestor_authority", "AUTHORIZES", "outcome_attestation"),
        },
        "assurance_claims": [
            "signed_manifest", "graph_integrity", "authorization_bound_mcp_action",
            "mcp_target_binding", "independent_mcp_outcome",
            "attested_mcp_outcome",
        ],
    },
    "authority_lifecycle": {
        "required_nodes": {
            "identity", "capability", "action_intent", "decision", "decision_receipt",
            "policy_version", "execution_authorization", "execution_receipt", "outcome_claim",
            "outcome_attestation", "attestor_authority", "governance_action", "governance_approval",
            "authority_event",
        },
        "required_edges": {
            ("identity", "AUTHENTICATES", "action_intent"),
            ("capability", "AUTHORIZES", "action_intent"),
            ("decision", "MINTS", "execution_authorization"),
            ("execution_authorization", "PRODUCES", "execution_receipt"),
            ("execution_receipt", "OBSERVED_BY", "outcome_claim"),
            ("outcome_attestation", "ATTESTS", "outcome_claim"),
            ("attestor_authority", "AUTHORIZES", "outcome_attestation"),
            ("attestor_authority", "DERIVED_FROM", "governance_action"),
            ("outcome_claim", "INFORMS", "authority_event"),
        },
        "assurance_claims": [
            "signed_manifest", "graph_integrity", "verified_signed_artifacts",
            "identity_bound_authority", "policy_bound_decision",
            "authorization_bound_execution", "independent_outcome_attestation",
            "governed_attestor_lineage", "authority_transition_provenance",
        ],
    },
}

def assurance_claims(profile: str) -> list[str]:
    spec = PROOF_PROFILES.get(profile)
    return list(spec.get("assurance_claims", [])) if spec else []

def profile_spec(profile: str) -> dict[str, Any] | None:
    return PROOF_PROFILES.get(profile)
