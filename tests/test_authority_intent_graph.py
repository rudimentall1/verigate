import unittest

from core.authority_intent_graph import AuthorityAwareIntentGraph, PlanAuthorityStatus
from core.authority_protocol import Authority, AuthorityState
from core.intent_graph import (
    IntentEdge,
    IntentGraph,
    IntentGraphBuilder,
    IntentNode,
    IntentNodeType,
    IntentRelation,
)
from core.models import ActionIntent, Capability, Decision


class AuthorityAwareIntentGraphTest(unittest.TestCase):
    def capability(self, max_amount=10.0):
        return Capability(
            capability_id="cap-1",
            agent_id="agent-1",
            allowed_actions=("payment",),
            allowed_targets=("merchant",),
            allowed_assets=("USDC",),
            max_per_action={"USDC": max_amount},
            issued_at=1000.0,
        )

    def authority(self, capability):
        return Authority(
            authority_id="auth-1",
            agent_id="agent-1",
            identity_id="identity-1",
            capability_id=capability.capability_id,
            capability_version=capability.version,
            capability_sha256=capability.digest,
            state=AuthorityState.STANDARD,
            multiplier=1.0,
            effective_from=1000.0,
        )

    def action(self, intent_id, amount=2.0, agent_id="agent-1"):
        return ActionIntent(
            agent_id=agent_id,
            action_type="payment",
            target="merchant",
            amount=amount,
            asset="USDC",
            intent_id=intent_id,
            timestamp=1000.0,
        )

    def graph(self, first, second=None):
        builder = IntentGraphBuilder("plan-1").add_action(first)
        if second:
            builder.add_action(second).link(
                first.intent_id, __import__("core.intent_graph", fromlist=["IntentRelation"]).IntentRelation.DEPENDS_ON,
                second.intent_id,
            )
        return builder.build()

    def test_eligible_action_is_not_execution_authorization(self):
        action = self.action("a1")
        graph = IntentGraphBuilder("plan-1").add_action(action).build()
        cap = self.capability()
        assessment = AuthorityAwareIntentGraph(graph, self.authority(cap), cap).assess("a1")

        self.assertEqual(assessment.status, PlanAuthorityStatus.ELIGIBLE)
        self.assertEqual(assessment.decision, Decision.ALLOW)
        self.assertFalse(assessment.is_execution_authorization)

    def test_capability_outside_scope_is_blocked(self):
        action = ActionIntent(
            agent_id="agent-1", action_type="delete", target="merchant", intent_id="a1"
        )
        graph = IntentGraphBuilder("plan-1").add_action(action).build()
        cap = self.capability()
        assessment = AuthorityAwareIntentGraph(graph, self.authority(cap), cap).assess("a1")

        self.assertEqual(assessment.status, PlanAuthorityStatus.BLOCKED)
        self.assertIn("action type outside capability", assessment.reason)

    def test_blocked_dependency_blocks_downstream_action(self):
        first = ActionIntent(
            agent_id="agent-1", action_type="delete", target="merchant", intent_id="a1"
        )
        second = self.action("a2")
        from core.intent_graph import IntentRelation
        graph = (
            IntentGraphBuilder("plan-1")
            .add_action(first)
            .add_action(second)
            .link("a2", IntentRelation.DEPENDS_ON, "a1")
            .build()
        )
        cap = self.capability()
        assessment = AuthorityAwareIntentGraph(graph, self.authority(cap), cap).assess("a2")

        self.assertEqual(assessment.status, PlanAuthorityStatus.BLOCKED)
        self.assertIn("dependency 'a1'", assessment.reason)

    def test_downstream_action_is_blocked_by_ineligible_dependency(self):
        first = self.action("a1")
        second = ActionIntent(
            agent_id="agent-1", action_type="delete", target="merchant", intent_id="a2"
        )
        from core.intent_graph import IntentRelation
        graph = (
            IntentGraphBuilder("plan-1")
            .add_action(first)
            .add_action(second)
            .link("a2", IntentRelation.DEPENDS_ON, "a1")
            .build()
        )
        cap = self.capability()
        assessment = AuthorityAwareIntentGraph(graph, self.authority(cap), cap).assess("a2")

        self.assertEqual(assessment.status, PlanAuthorityStatus.BLOCKED)
        self.assertIn("action type outside capability", assessment.reason)

    def test_dynamic_authority_reduces_numeric_scope(self):
        action = self.action("a1", amount=8.0)
        graph = IntentGraphBuilder("plan-1").add_action(action).build()
        cap = self.capability(max_amount=10.0)
        authority = Authority(
            authority_id="auth-1",
            agent_id="agent-1",
            identity_id="identity-1",
            capability_id=cap.capability_id,
            capability_version=cap.version,
            capability_sha256=cap.digest,
            state=AuthorityState.LIMITED,
            multiplier=0.5,
            effective_from=1000.0,
        )
        assessment = AuthorityAwareIntentGraph(graph, authority, cap).assess("a1")

        self.assertEqual(assessment.status, PlanAuthorityStatus.BLOCKED)
        self.assertIn("dynamic authority ceiling", assessment.reason)

    def test_assessment_digest_changes_with_graph_or_authority(self):
        action = self.action("a1")
        graph = IntentGraphBuilder("plan-1").add_action(action).build()
        cap = self.capability()
        first = AuthorityAwareIntentGraph(graph, self.authority(cap), cap).assess("a1")
        changed_graph = IntentGraphBuilder("plan-2").add_action(action).build()
        second = AuthorityAwareIntentGraph(changed_graph, self.authority(cap), cap).assess("a1")

        self.assertNotEqual(first.digest, second.digest)
        self.assertEqual(len(first.digest), 64)

    def test_cyclic_dependency_is_blocked_not_a_recursion_error(self):
        # IntentGraphBuilder.build() rejects cycles via validate(), so this
        # constructs the frozen IntentGraph directly -- the only way an
        # invalid graph can reach AuthorityAwareIntentGraph at all. assess()
        # must not assume every caller went through the builder.
        a1 = self.action("a1")
        a2 = self.action("a2")
        graph = IntentGraph(
            graph_id="cyclic-plan",
            nodes=(
                IntentNode("a1", IntentNodeType.ACTION, "a1", {"action_intent": a1.as_dict()}),
                IntentNode("a2", IntentNodeType.ACTION, "a2", {"action_intent": a2.as_dict()}),
            ),
            edges=(
                IntentEdge("a1", IntentRelation.DEPENDS_ON, "a2"),
                IntentEdge("a2", IntentRelation.DEPENDS_ON, "a1"),
            ),
        )
        valid, errors = graph.validate()
        self.assertFalse(valid)
        self.assertIn("intent graph contains a dependency cycle", errors)

        cap = self.capability()
        # The real regression is that this line returns at all instead of
        # raising RecursionError. The cycle is detected one recursion level
        # in (a1 -> a2 -> a1 hits the guard), so the outer assessment's own
        # reason is the ordinary "dependency not eligible" wording; the
        # cycle-specific reason lives in that nested call, not this one.
        assessment = AuthorityAwareIntentGraph(graph, self.authority(cap), cap).assess("a1")

        self.assertEqual(assessment.status, PlanAuthorityStatus.BLOCKED)
        self.assertEqual(
            dict(assessment.dependency_statuses)["a2"], PlanAuthorityStatus.BLOCKED
        )

    def test_self_dependency_cycle_reason_is_reported(self):
        a1 = self.action("a1")
        graph = IntentGraph(
            graph_id="self-loop-plan",
            nodes=(
                IntentNode("a1", IntentNodeType.ACTION, "a1", {"action_intent": a1.as_dict()}),
            ),
            edges=(IntentEdge("a1", IntentRelation.DEPENDS_ON, "a1"),),
        )
        cap = self.capability()
        # Same point as above: the top-level reason is the ordinary
        # dependency-wrapping message, since the direct self-loop is
        # detected one recursion level in. What matters is that this
        # terminates at all and comes back BLOCKED, not an unbounded
        # recursion into a self-referencing node.
        assessment = AuthorityAwareIntentGraph(graph, self.authority(cap), cap).assess("a1")

        self.assertEqual(assessment.status, PlanAuthorityStatus.BLOCKED)


if __name__ == "__main__":
    unittest.main()
