import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key
from core.engine import GuardrailEngine
from core.models import ActionIntent
from core.policy import Policy
from core.storage import Storage


class ExecutionGraphPolicyTest(unittest.TestCase):
    def test_validly_signed_malicious_graph_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            policy_path = root / "policy.yaml"
            policy_path.write_text(
                "allowed_action_types: [mcp.tool.call]\n"
                "execution_graph:\n"
                "  module: approved-module\n"
                "  hook: policy-hook\n"
                "  router: safe-router\n"
                "  target: orders.create\n",
                encoding="utf-8",
            )
            private = root / "issuer.key"
            public = root / "issuer.pub"
            generate_keypair(private, public)
            storage = Storage(root / "audit.db")
            try:
                engine = GuardrailEngine(Policy.load(policy_path), storage)
                action = ActionIntent(
                    agent_id="graph-agent",
                    action_type="mcp.tool.call",
                    target="orders.create",
                    purpose="order execution",
                    metadata={
                        "execution_graph": {
                            "module": "malicious-module",
                            "hook": "policy-hook",
                            "router": "safe-router",
                            "target": "orders.create",
                        }
                    },
                )
                result = engine._authorize_control_plane(
                    action, load_private_key(private)
                )
                decision = result["decision_receipt"]["payload"]["decision"]
                self.assertEqual(decision["decision"], "BLOCK")
                self.assertEqual(result["execution_authorization"], None)
                self.assertTrue(any(
                    r["rule"] == "execution_graph_not_allowed"
                    for r in decision["matched_rules"]
                ))
            finally:
                storage.close()

    def test_missing_graph_is_blocked_when_policy_requires_it(self):
        policy = Policy(execution_graph={"module": "approved-module"})
        action = ActionIntent(
            agent_id="graph-agent",
            action_type="mcp.tool.call",
            target="orders.create",
        )
        storage = Storage(":memory:")
        try:
            engine = GuardrailEngine(policy, storage)
            decision = engine.evaluate_action(action)
            self.assertEqual(decision.decision.value, "BLOCK")
        finally:
            storage.close()


if __name__ == "__main__":
    unittest.main()
