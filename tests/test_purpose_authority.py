import unittest
from core.engine import GuardrailEngine
from core.models import ActionIntent, Capability, Decision
from core.policy import Policy
from core.storage import Storage

class TestPurposeAuthority(unittest.TestCase):
    def _check(self, purpose):
        policy = Policy(allowed_purposes=["fulfill_order"], raw={"allowed_purposes": ["fulfill_order"]})
        storage = Storage(":memory:")
        try:
            engine = GuardrailEngine(policy, storage)
            action = ActionIntent(agent_id="agent", action_type="api.request", target="orders", purpose=purpose)
            return engine.evaluate_action(action)
        finally:
            storage.close()

    def test_policy_allows_matching_purpose(self):
        decision = self._check("fulfill_order")
        self.assertEqual(decision.decision, Decision.ALLOW)

    def test_policy_blocks_wrong_purpose(self):
        decision = self._check("export_customer_data")
        self.assertEqual(decision.decision, Decision.BLOCK)
        self.assertTrue(any(m.rule_id == "purpose_not_allowed" for m in decision.matched_rules))

if __name__ == "__main__":
    unittest.main()




class TestContextAuthority(unittest.TestCase):
    def _check(self, context):
        policy = Policy(context_constraints={"region": "EU", "channel": ["web", "mcp"]}, raw={"context_constraints": {"region": "EU", "channel": ["web", "mcp"]}})
        storage = Storage(":memory:")
        try:
            engine = GuardrailEngine(policy, storage)
            action = ActionIntent(agent_id="agent", action_type="api.request", target="orders", declared_context=context)
            return engine.evaluate_action(action)
        finally:
            storage.close()

    def test_matching_context_is_allowed(self):
        self.assertEqual(self._check({"region": "EU", "channel": "web"}).decision, Decision.ALLOW)

    def test_context_mismatch_is_blocked(self):
        decision = self._check({"region": "US", "channel": "web"})
        self.assertEqual(decision.decision, Decision.BLOCK)
        self.assertTrue(any(m.rule_id == "context_not_allowed" for m in decision.matched_rules))


class TestCapabilityConstraints(unittest.TestCase):
    def test_capability_bounds_purpose_and_context(self):
        capability = Capability(capability_id="cap-1", agent_id="agent", allowed_actions=("api.request",), allowed_purposes=("fulfill_order",), context_constraints={"region": "EU", "channel": ("web", "mcp")})
        allowed = ActionIntent(agent_id="agent", action_type="api.request", target="orders", purpose="fulfill_order", declared_context={"region": "EU", "channel": "web"})
        denied = ActionIntent(agent_id="agent", action_type="api.request", target="orders", purpose="export_data", declared_context={"region": "US", "channel": "web"})
        self.assertTrue(capability.permits(allowed)[0])
        self.assertFalse(capability.permits(denied)[0])
