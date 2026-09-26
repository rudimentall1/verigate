import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.engine import GuardrailEngine
from core.models import ActionIntent, Decision, Capability
from core.policy import Policy
from core.storage import Storage
from core.authority_state import DynamicAuthorityService
from core.authorization import AuthorizationService
from enforcement.tool import ToolExecutionAdapter


class ZeroClickToolAbuseTest(unittest.TestCase):
    """Regression contract for untrusted-input -> tool -> destination abuse."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.policy_path = root / "policy.yaml"
        self.private = root / "issuer.key"
        self.public = root / "issuer.pub"
        self.db = root / "audit.db"
        self.policy_path.write_text(
            "allowed_action_types:\n  - mcp.tool.call\nallowed_targets:\n  - http.fetch\nallowed_destinations:\n  - https://api.internal.example\nblocked_destinations:\n  - https://attacker.example\n",
            encoding="utf-8",
        )
        generate_keypair(self.private, self.public)
        self.storage = Storage(self.db)
        self.policy = Policy.load(self.policy_path)
        self.engine = GuardrailEngine(self.policy, self.storage)
        self.private_key = load_private_key(self.private)
        self.public_key = load_public_key(self.public)

    def tearDown(self):
        self.storage.close()
        self.tmpdir.cleanup()

    def _action(self, destination):
        return ActionIntent(
            agent_id="agent-zero-click",
            action_type="mcp.tool.call",
            target="http.fetch",
            purpose="retrieve approved internal resource",
            declared_context={"input_trust": "untrusted"},
            metadata={
                "tool_invocation": {
                    "tool": "http.fetch",
                    "destination": destination,
                },
                "arguments": {"url": destination + "/records"},
            },
        )

    def test_untrusted_input_cannot_redirect_tool_to_attacker(self):
        action = self._action("https://attacker.example")
        decision = self.engine.evaluate_action(action)

        self.assertEqual(decision.decision, Decision.BLOCK)
        self.assertTrue(
            any(m.rule_id in {"destination_blocked", "destination_not_allowed"} for m in decision.matched_rules)
        )

        capability = Capability(
            capability_id="cap-zero-click",
            agent_id=action.agent_id,
            allowed_actions=("mcp.tool.call",),
            allowed_targets=("http.fetch",),
        )
        self.storage.register_capability(capability)
        authority = DynamicAuthorityService(self.storage).snapshot(
            action.agent_id, capability.capability_id
        )
        result = AuthorizationService().issue(
            action,
            decision,
            self.policy.digest,
            self.private_key,
            capability=capability,
            authority=authority,
            policy=self.policy,
        )
        self.assertIsNone(result["execution_authorization"])

    def test_allowed_destination_can_execute_through_registered_tool(self):
        action = self._action("https://api.internal.example")
        decision = self.engine.evaluate_action(action)
        self.assertEqual(decision.decision, Decision.ALLOW)

        capability = Capability(
            capability_id="cap-zero-click-safe",
            agent_id=action.agent_id,
            allowed_actions=("mcp.tool.call",),
            allowed_targets=("http.fetch",),
        )
        self.storage.register_capability(capability)
        authority = DynamicAuthorityService(self.storage).snapshot(
            action.agent_id, capability.capability_id
        )
        auth = AuthorizationService().issue(
            action,
            decision,
            self.policy.digest,
            self.private_key,
            capability=capability,
            authority=authority,
            policy=self.policy,
        )["execution_authorization"]

        calls = []
        adapter = ToolExecutionAdapter(
            self.storage,
            self.public_key,
            {"http.fetch": lambda signed_action: calls.append(signed_action) or "fetched"},
        )
        self.assertEqual(adapter.execute_registered(auth), "fetched")
        self.assertEqual(
            calls[0]["metadata"]["tool_invocation"]["destination"],
            "https://api.internal.example",
        )


if __name__ == "__main__":
    unittest.main()

