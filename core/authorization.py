"""Protocol-agnostic authorization artifact minting.

Policy evaluation can remain vertical-specific, while every integration uses
this same cryptographic path to turn a decision into portable proof and, for
ALLOW, a one-time execution capability.
"""
from __future__ import annotations

from typing import Any

from .models import ActionIntent, AgentIdentity, Capability, Decision, GuardrailDecision
from .capabilities import CapabilityRegistry
from .authority_state import AuthoritySnapshot
from .effective_authority import effective_authority
from .policy import Policy
from .external_state import external_state_requirement_for_action
from .authority_intent_graph import IntentAuthorityAssessment, PlanAuthorityStatus
from attest.receipt import issue_execution_authorization, sign_receipt


class AuthorizationService:
    """Mint decision receipts and execution capabilities for any action."""

    def issue_decision_receipt(
        self,
        action: ActionIntent,
        decision: GuardrailDecision,
        policy_digest: str,
        private_key: Any,
        *,
        signed_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a signed decision without granting execution authority."""
        if action.intent_id != decision.intent_id or action.agent_id != decision.agent_id:
            raise ValueError("action and decision identities do not match")
        if decision.context_digest and decision.context_digest != action.context_digest:
            raise ValueError("action context does not match the authorized decision")
        receipt = sign_receipt(
            action,
            decision,
            policy_digest,
            private_key,
            signed_policy_version=signed_policy,
        )
        return {
            "decision_receipt": receipt.as_dict(),
            "execution_authorization": None,
        }

    def issue(
        self,
        action: ActionIntent,
        decision: GuardrailDecision,
        policy_digest: str,
        private_key: Any,
        *,
        nonce: str | None = None,
        ttl_seconds: int = 300,
        capability: Capability | None = None,
        capability_registry: CapabilityRegistry | None = None,
        identity: AgentIdentity | None = None,
        authority: AuthoritySnapshot | None = None,
        authority_policy: Any | None = None,
        policy: Policy | None = None,
        signed_policy: dict[str, Any] | None = None,
        authority_assessment: IntentAuthorityAssessment | None = None,
    ) -> dict[str, Any]:
        if action.intent_id != decision.intent_id or action.agent_id != decision.agent_id:
            raise ValueError("action and decision identities do not match")
        if decision.context_digest and decision.context_digest != action.context_digest:
            raise ValueError("action context does not match the authorized decision")

        # The policy object is an input to effective-authority calculation, so
        # it must be the exact policy named by the decision receipt. Otherwise
        # a low-level caller could claim digest X while using policy Y to mint
        # executable authority. Fail closed before signing any artifact.
        if policy is not None and policy.digest != policy_digest:
            raise PermissionError("supplied policy does not match policy digest")
        if signed_policy is not None:
            signed_payload = signed_policy.get("payload")
            if not isinstance(signed_payload, dict):
                raise PermissionError("invalid signed policy version")
            if signed_payload.get("policy_sha256") != policy_digest:
                raise PermissionError("signed policy version does not match policy digest")
            if policy is not None and signed_payload.get("policy_sha256") != policy.digest:
                raise PermissionError("signed policy version does not match supplied policy")

        if authority_assessment is not None:
            if authority_assessment.status != PlanAuthorityStatus.ELIGIBLE:
                raise PermissionError("authority assessment is not execution-eligible")
            if authority_assessment.is_execution_authorization:
                raise ValueError("authority assessment cannot itself be execution authorization")
            if authority_assessment.intent_id != action.intent_id or authority_assessment.agent_id != action.agent_id:
                raise ValueError("authority assessment does not match action")

        # A capability is the authority source for the exact action. Keep the
        # optional parameter during migration so existing integrations remain
        # compatible while new control-plane flows can require it.
        if capability is not None:
            if (
                action.requested_capability is not None
                and action.requested_capability != capability.capability_id
            ):
                raise PermissionError("requested capability does not match supplied capability")
            if capability.delegated_from is not None:
                if capability_registry is None:
                    raise PermissionError(
                        "delegated capability requires registry-backed authority-chain verification"
                    )
                resolved = capability_registry.resolve(capability.capability_id)
                if resolved.digest != capability.digest:
                    raise PermissionError("supplied capability does not match registered capability")
            permitted, reason = capability.permits(action)
            if not permitted:
                raise PermissionError(reason)
        if identity is not None and identity.agent_id != action.agent_id:
            raise PermissionError("identity agent mismatch")
        if capability is not None and capability.identity_id is not None:
            if identity is None or capability.identity_id != identity.key_id:
                raise PermissionError("capability identity mismatch")
        if capability is not None and authority is not None:
            if authority.agent_id != action.agent_id:
                raise PermissionError("authority agent mismatch")
            if authority.capability_id != capability.capability_id:
                raise PermissionError("authority capability mismatch")
            if authority_policy is not None:
                expected_multiplier = authority_policy.multiplier(authority.state)
                if authority.multiplier != expected_multiplier:
                    raise PermissionError("authority multiplier does not match authority state")
            if authority.state.value == "SUSPENDED" or authority.multiplier <= 0:
                raise PermissionError("suspended authority cannot mint execution authorization")

        receipt = sign_receipt(
            action,
            decision,
            policy_digest,
            private_key,
            signed_policy_version=signed_policy,
        )
        execution = None
        effective = None
        if decision.decision == Decision.ALLOW:
            if capability is None or authority is None or policy is None:
                raise PermissionError(
                    "executable authorization requires capability, dynamic authority, and policy binding"
                )
            effective = effective_authority(action, capability, policy, authority)
            execution_graph = dict((action.metadata or {}).get("execution_graph") or {})
            genesis_authority = None
            if authority_assessment is not None:
                genesis_authority = {
                    "protocol": "genesis-2.0",
                    "intent_graph_digest": authority_assessment.graph_digest,
                    "intent_graph_node_id": authority_assessment.node_id,
                    "authority_assessment_digest": authority_assessment.digest,
                    "authority_digest": authority_assessment.authority_digest,
                    "capability_digest": authority_assessment.capability_digest,
                }
            execution = issue_execution_authorization(
                receipt,
                private_key,
                nonce=nonce or action.intent_id,
                ttl_seconds=ttl_seconds,
                capability_id=capability.capability_id if capability else None,
                capability_version=capability.version if capability else None,
                capability_sha256=capability.digest if capability else None,
                identity_id=identity.key_id if identity else None,
                identity_sha256=identity.digest if identity else None,
                authority_state=authority.as_dict() if authority else None,
                authority_state_sha256=authority.digest if authority else None,
                authority_multiplier=authority.multiplier if authority else None,
                authority_ledger_head_hash=authority.ledger_head_hash if authority else None,
                authority_policy_sha256=authority.authority_policy_sha256 if authority else None,
                authority_policy=authority_policy.as_dict() if authority and authority_policy else None,
                effective_authority=effective,
                execution_graph=execution_graph,
                genesis_authority=genesis_authority,
                external_state_required=(policy.require_external_state_binding or external_state_requirement_for_action(policy.external_state_requirements, action.as_dict()) is not None),
                external_state_requirement=external_state_requirement_for_action(policy.external_state_requirements, action.as_dict()),
            )

        return {
            "decision_receipt": receipt.as_dict(),
            "execution_authorization": execution.as_dict() if execution else None,
        }
