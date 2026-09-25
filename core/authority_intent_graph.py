"""Genesis 2.0 Authority-aware Intent Graph.

The Intent Graph describes a plan. This module evaluates whether individual
actions in that plan are within the agent's current authority envelope.

A positive assessment is eligibility for authorization, never authorization
itself. Exact execution still requires the existing authorization boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .authority_protocol import Authority, AuthorityState, authority_ceiling_allows, canonical_digest
from .intent_graph import IntentGraph, IntentNodeType
from .models import ActionIntent, Capability, Decision


class PlanAuthorityStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class IntentAuthorityAssessment:
    """Deterministic evidence that one graph action is within current authority."""

    graph_id: str
    graph_digest: str
    node_id: str
    intent_id: str
    agent_id: str
    authority_digest: str
    capability_digest: str
    status: PlanAuthorityStatus
    decision: Decision
    reason: str
    dependency_statuses: tuple[tuple[str, PlanAuthorityStatus], ...] = ()

    @property
    def digest(self) -> str:
        return canonical_digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "graph_digest": self.graph_digest,
            "node_id": self.node_id,
            "intent_id": self.intent_id,
            "agent_id": self.agent_id,
            "authority_digest": self.authority_digest,
            "capability_digest": self.capability_digest,
            "status": self.status.value,
            "decision": self.decision.value,
            "reason": self.reason,
            "dependency_statuses": [
                [node_id, status.value] for node_id, status in self.dependency_statuses
            ],
        }

    @property
    def is_execution_authorization(self) -> bool:
        """Explicitly document the security boundary."""
        return False


class AuthorityAwareIntentGraph:
    """Resolve graph actions against one exact Authority + Capability pair."""

    def __init__(self, graph: IntentGraph, authority: Authority, capability: Capability):
        self.graph = graph
        self.authority = authority
        self.capability = capability
        if capability.agent_id != authority.agent_id:
            raise ValueError("capability agent does not match authority agent")
        if capability.capability_id != authority.capability_id:
            raise ValueError("capability does not match authority")
        if capability.version != authority.capability_version:
            raise ValueError("capability version does not match authority")
        if capability.digest != authority.capability_sha256:
            raise ValueError("capability digest does not match authority")

    def assess(self, node_id: str) -> IntentAuthorityAssessment:
        node = self.graph.node(node_id)
        if node.node_type != IntentNodeType.ACTION:
            raise ValueError("authority assessment requires an ACTION node")

        action = self._action(node_id)
        dependency_statuses: list[tuple[str, PlanAuthorityStatus]] = []
        for dependency_id in self.graph.dependencies_of(node_id):
            dependency = self.assess(dependency_id)
            dependency_statuses.append((dependency_id, dependency.status))
            if dependency.status != PlanAuthorityStatus.ELIGIBLE:
                return self._assessment(
                    node_id,
                    action,
                    PlanAuthorityStatus.BLOCKED,
                    f"dependency '{dependency_id}' is not authority-eligible",
                    tuple(dependency_statuses),
                )

        if self.authority.state == AuthorityState.SUSPENDED:
            return self._assessment(
                node_id, action, PlanAuthorityStatus.BLOCKED,
                "authority is suspended", tuple(dependency_statuses),
            )

        if action.agent_id != self.authority.agent_id:
            return self._assessment(
                node_id, action, PlanAuthorityStatus.BLOCKED,
                "action agent does not match authority", tuple(dependency_statuses),
            )

        if action.requested_capability and action.requested_capability != self.authority.capability_id:
            return self._assessment(
                node_id, action, PlanAuthorityStatus.BLOCKED,
                "requested capability does not match authority", tuple(dependency_statuses),
            )

        permitted, reason = self.capability.permits(action)
        if not permitted:
            return self._assessment(
                node_id, action, PlanAuthorityStatus.BLOCKED,
                reason, tuple(dependency_statuses),
            )

        if action.amount is not None:
            static_limit = self.capability.max_per_action.get(action.asset or "")
            if static_limit is not None and not authority_ceiling_allows(
                static_limit, self.authority.multiplier, action.amount
            ):
                return self._assessment(
                    node_id, action, PlanAuthorityStatus.BLOCKED,
                    "action exceeds current dynamic authority ceiling",
                    tuple(dependency_statuses),
                )

        return self._assessment(
            node_id, action, PlanAuthorityStatus.ELIGIBLE,
            "action is within current authority and dependencies are eligible",
            tuple(dependency_statuses),
        )

    def assess_all(self) -> tuple[IntentAuthorityAssessment, ...]:
        return tuple(self.assess(node.node_id) for node in self.graph.actions())

    def _action(self, node_id: str) -> ActionIntent:
        payload = self.graph.node(node_id).metadata.get("action_intent")
        if not isinstance(payload, dict):
            raise ValueError(f"ACTION node '{node_id}' has no ActionIntent payload")
        return ActionIntent(**payload)

    def _assessment(
        self,
        node_id: str,
        action: ActionIntent,
        status: PlanAuthorityStatus,
        reason: str,
        dependency_statuses: tuple[tuple[str, PlanAuthorityStatus], ...],
    ) -> IntentAuthorityAssessment:
        return IntentAuthorityAssessment(
            graph_id=self.graph.graph_id,
            graph_digest=self.graph.digest,
            node_id=node_id,
            intent_id=action.intent_id,
            agent_id=action.agent_id,
            authority_digest=self.authority.digest,
            capability_digest=self.capability.digest,
            status=status,
            decision=Decision.ALLOW if status == PlanAuthorityStatus.ELIGIBLE else Decision.BLOCK,
            reason=reason,
            dependency_statuses=dependency_statuses,
        )
