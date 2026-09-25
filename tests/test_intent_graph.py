import unittest

from core.intent_graph import (
    IntentGraphBuilder,
    IntentNodeType,
    IntentRelation,
)
from core.models import ActionIntent


class IntentGraphTest(unittest.TestCase):
    def action(self, intent_id: str) -> ActionIntent:
        return ActionIntent(
            agent_id="agent-1",
            action_type="api.call",
            target="service",
            intent_id=intent_id,
        )

    def test_builds_goal_to_actions_and_hashes(self):
        graph = (
            IntentGraphBuilder("plan-1")
            .add_node("goal-1", IntentNodeType.GOAL, "complete purchase")
            .add_node("intent-1", IntentNodeType.INTENT, "purchase workflow")
            .add_node("sub-1", IntentNodeType.SUB_INTENT, "prepare payment")
            .add_action(self.action("action-1"))
            .add_action(self.action("action-2"))
            .add_node("effect-1", IntentNodeType.CONSEQUENCE, "resource acquired")
            .link("goal-1", IntentRelation.CONTAINS, "intent-1")
            .link("intent-1", IntentRelation.CONTAINS, "sub-1")
            .link("sub-1", IntentRelation.CONTAINS, "action-1")
            .link("sub-1", IntentRelation.CONTAINS, "action-2")
            .link("action-1", IntentRelation.PRODUCES, "effect-1")
            .link("action-2", IntentRelation.DEPENDS_ON, "action-1")
            .build()
        )
        valid, errors = graph.validate()
        self.assertTrue(valid, errors)
        self.assertEqual([n.node_id for n in graph.actions()], ["action-1", "action-2"])
        self.assertEqual(graph.dependencies_of("action-2"), ("action-1",))
        self.assertEqual(len(graph.digest), 64)

    def test_dependency_cycle_is_rejected(self):
        builder = (
            IntentGraphBuilder("plan-2")
            .add_node("a", IntentNodeType.ACTION, "a")
            .add_node("b", IntentNodeType.ACTION, "b")
            .link("a", IntentRelation.DEPENDS_ON, "b")
            .link("b", IntentRelation.DEPENDS_ON, "a")
        )
        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            builder.build()

    def test_graph_is_not_authorization(self):
        graph = (
            IntentGraphBuilder("plan-3")
            .add_action(self.action("action-1"))
            .build()
        )
        self.assertEqual(len(graph.actions()), 1)
        # The graph contains an action description, but no execution capability.
        self.assertFalse(any("authorization" in node.metadata for node in graph.nodes))


if __name__ == "__main__":
    unittest.main()
