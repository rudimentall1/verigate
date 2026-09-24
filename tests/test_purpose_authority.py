import unittest
from core.engine import GuardrailEngine
from core.models import ActionIntent, Decision
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


