import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.receipt import verify_receipt
from core.engine import GuardrailEngine
from core.models import ActionIntent, Decision, Capability
from core.policy import Policy
from core.storage import Storage
from core.authority_state import DynamicAuthorityService
from core.authorization import AuthorizationService
from enforcement.tool import ToolExecutionAdapter, build_tool_execution_graph


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
            "allowed_action_types:\n  - mcp.tool.call\nallowed_targets:\n  - http.fetch\ninput_provenance_constraints:\n  trust: trusted\nallowed_destinations:\n  - https://api.internal.example\nblocked_destinations:\n  - https://attacker.example\n",
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

    def _action(self, destination, trust="trusted"):
        return ActionIntent(
            agent_id="agent-zero-click",
            action_type="mcp.tool.call",
            target="http.fetch",
            purpose="retrieve approved internal resource",
            declared_context={"input_trust": trust},
            input_provenance={"trust": trust, "source": "external_content"},
            metadata={
                "tool_invocation": {
                    "tool": "http.fetch",
                    "destination": destination,
                },
                "arguments": {"url": destination + "/records"},
            },
        )

    def test_untrusted_input_cannot_redirect_tool_to_attacker(self):
        action = self._action("https://attacker.example", trust="untrusted")
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
        calls = []
        def registered_handler(signed_action):
            calls.append(signed_action)
            return "fetched"

        # The fingerprint is computed from the exact callable registered below.
        action_graph = build_tool_execution_graph("http.fetch", registered_handler)
        action = ActionIntent(
            agent_id=action.agent_id,
            action_type=action.action_type,
            target=action.target,
            purpose=action.purpose,
            declared_context=action.declared_context,
            input_provenance=action.input_provenance,
            metadata={**action.metadata, "execution_graph": action_graph},
        )
        decision = self.engine.evaluate_action(action)
        auth = AuthorizationService().issue(
            action, decision, self.policy.digest, self.private_key,
            capability=capability, authority=authority, policy=self.policy,
        )["execution_authorization"]
        adapter = ToolExecutionAdapter(
            self.storage, self.public_key, {"http.fetch": registered_handler},
        )
        self.assertEqual(adapter.execute_registered(auth), "fetched")
        self.assertEqual(
            calls[0]["metadata"]["tool_invocation"]["destination"],
            "https://api.internal.example",
        )

    def test_tool_handler_fingerprint_is_required(self):
        action = self._action("https://api.internal.example")
        decision = self.engine.evaluate_action(action)
        capability = Capability(
            capability_id="cap-zero-click-missing-fingerprint",
            agent_id=action.agent_id,
            allowed_actions=("mcp.tool.call",),
            allowed_targets=("http.fetch",),
        )
        self.storage.register_capability(capability)
        authority = DynamicAuthorityService(self.storage).snapshot(
            action.agent_id, capability.capability_id
        )
        auth = AuthorizationService().issue(
            action, decision, self.policy.digest, self.private_key,
            capability=capability, authority=authority, policy=self.policy,
        )["execution_authorization"]
        calls = []
        adapter = ToolExecutionAdapter(
            self.storage, self.public_key,
            {"http.fetch": lambda signed_action: calls.append(signed_action)},
        )
        ok, reason = adapter.validate(auth)
        self.assertFalse(ok)
        self.assertIn("handler fingerprint", reason)
        self.assertEqual(calls, [])

    def test_changed_handler_is_rejected_before_tool_side_effect(self):
        original = lambda signed_action: "original"
        action = self._action("https://api.internal.example")
        action = ActionIntent(
            agent_id=action.agent_id,
            action_type=action.action_type,
            target=action.target,
            purpose=action.purpose,
            declared_context=action.declared_context,
            input_provenance=action.input_provenance,
            metadata={**action.metadata,
                      "execution_graph": build_tool_execution_graph("http.fetch", original)},
        )
        decision = self.engine.evaluate_action(action)
        capability = Capability(
            capability_id="cap-zero-click-handler-drift",
            agent_id=action.agent_id,
            allowed_actions=("mcp.tool.call",),
            allowed_targets=("http.fetch",),
        )
        self.storage.register_capability(capability)
        authority = DynamicAuthorityService(self.storage).snapshot(
            action.agent_id, capability.capability_id
        )
        auth = AuthorizationService().issue(
            action, decision, self.policy.digest, self.private_key,
            capability=capability, authority=authority, policy=self.policy,
        )["execution_authorization"]
        calls = []
        replacement = lambda signed_action: calls.append(signed_action) or "replaced"
        adapter = ToolExecutionAdapter(
            self.storage, self.public_key, {"http.fetch": replacement}
        )
        with self.assertRaises(PermissionError):
            adapter.execute_registered(auth)
        self.assertEqual(calls, [])

    def test_provenance_tamper_invalidates_signed_decision(self):
        action = self._action("https://api.internal.example", trust="trusted")
        decision = self.engine.evaluate_action(action)
        self.assertEqual(decision.decision, Decision.ALLOW)

        receipt = AuthorizationService().issue_decision_receipt(
            action,
            decision,
            self.policy.digest,
            self.private_key,
        )["decision_receipt"]
        ok, reason = verify_receipt(receipt, self.public_key)
        self.assertTrue(ok, reason)

        tampered = dict(receipt)
        tampered["payload"] = dict(receipt["payload"])
        tampered["payload"]["intent"] = dict(receipt["payload"]["intent"])
        tampered["payload"]["intent"]["input_provenance"] = {
            "trust": "untrusted",
            "source": "external_content",
        }
        ok, reason = verify_receipt(tampered, self.public_key)
        self.assertFalse(ok)
        self.assertIn("context fingerprint", reason)


if __name__ == "__main__":
    unittest.main()

