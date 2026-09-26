import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authorization import AuthorizationService
from core.models import ActionIntent, Capability, Decision, GuardrailDecision
from core.storage import Storage
from core.authority_state import DynamicAuthorityService
from core.policy import Policy
from enforcement.http import HTTPExecutionAdapter
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter
from enforcement.tool import ToolExecutionAdapter, _handler_fingerprint


class ExecutionFabricTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.private = root / "issuer.key"
        self.public = root / "issuer.pub"
        self.db = root / "audit.db"
        generate_keypair(self.private, self.public)
        self.storage = Storage(self.db)
        self.private_key = load_private_key(self.private)
        self.public_key = load_public_key(self.public)

    def tearDown(self):
        self.storage.close()
        self.tmpdir.cleanup()

    def _auth(self, action: ActionIntent):
        capability = Capability(
            capability_id=f"cap-fabric-{action.intent_id}",
            agent_id=action.agent_id,
            allowed_actions=(action.action_type,),
            allowed_targets=(action.target,),
        )
        self.storage.register_capability(capability)
        authority = DynamicAuthorityService(self.storage).snapshot(
            action.agent_id, capability.capability_id
        )
        policy = Policy()
        decision = GuardrailDecision(
            action.intent_id, action.agent_id, Decision.ALLOW, ()
        )
        return AuthorizationService().issue(
            action,
            decision,
            policy.digest,
            self.private_key,
            nonce=action.intent_id,
            capability=capability,
            authority=authority,
            policy=policy,
        )["execution_authorization"]

    def test_tool_execution_uses_signed_action_arguments(self):
        action = ActionIntent(
            agent_id="tool-agent",
            action_type="mcp.tool.call",
            target="github.create_issue",
            resource="repo:verigate",
            metadata={"arguments": {"title": "signed-title"}},
        )
        auth = self._auth(action)
        calls = []
        adapter = ToolExecutionAdapter(
            self.storage,
            self.public_key,
            {"github.create_issue": lambda signed_action: calls.append(signed_action) or "ok"},
        )
        self.assertEqual(adapter.execute_registered(auth), "ok")
        self.assertEqual(calls[0]["metadata"]["arguments"]["title"], "signed-title")
        self.assertEqual(adapter.consume(auth), (False, "execution authorization already consumed"))

    def test_unregistered_tool_cannot_consume_authority(self):
        action = ActionIntent(
            agent_id="tool-agent",
            action_type="mcp.tool.call",
            target="dangerous.delete_all",
        )
        auth = self._auth(action)
        adapter = ToolExecutionAdapter(self.storage, self.public_key, {})
        ok, reason = adapter.consume(auth)
        self.assertFalse(ok)
        self.assertIn("not registered", reason)

    def test_registered_handler_substitution_is_blocked_before_side_effect(self):
        def trusted_handler(_action):
            return "trusted"

        def malicious_handler(_action):
            return "attacker"

        target = "github.create_issue"
        action = ActionIntent(
            agent_id="tool-agent",
            action_type="mcp.tool.call",
            target=target,
            metadata={
                "arguments": {"title": "signed"},
                "execution_graph": {
                    "module": "enforcement.tool",
                    "hook": "ToolExecutionAdapter",
                    "router": "ExecutionRouter",
                    "target": target,
                    "handler_sha256": _handler_fingerprint(trusted_handler),
                },
            },
        )
        auth = self._auth(action)
        adapter = ToolExecutionAdapter(
            self.storage,
            self.public_key,
            {target: trusted_handler},
        )
        adapter.handlers[target] = malicious_handler

        router = ExecutionRouter(
            NetworkRegistry(),
            self.storage,
            self.public_key,
            generic_adapters={"mcp.tool.call": adapter},
        )
        side_effects = []
        with self.assertRaises(ValueError):
            router.execute(auth, lambda signed_action: side_effects.append(signed_action) or "sent")
        self.assertEqual(side_effects, [])

    def test_transitive_execution_claim_is_rejected_by_direct_only_tool_adapter(self):
        target = "github.create_issue"
        side_effects = []

        def handler(_signed_action):
            side_effects.append("child-side-effect")
            return "ok"

        action = ActionIntent(
            agent_id="tool-agent",
            action_type="mcp.tool.call",
            target=target,
            metadata={
                "arguments": {"title": "signed"},
                "execution_graph": {
                    "module": "enforcement.tool",
                    "hook": "ToolExecutionAdapter",
                    "router": "ExecutionRouter",
                    "target": target,
                    "enforcement_scope": "transitive",
                    "handler_sha256": _handler_fingerprint(handler),
                },
            },
        )
        auth = self._auth(action)
        adapter = ToolExecutionAdapter(
            self.storage,
            self.public_key,
            {target: handler},
        )
        router = ExecutionRouter(
            NetworkRegistry(),
            self.storage,
            self.public_key,
            generic_adapters={"mcp.tool.call": adapter},
        )

        with self.assertRaises(ValueError) as exc:
            router.execute(auth, lambda signed_action: side_effects.append(signed_action) or "sent")
        self.assertIn("transitive enforcement", str(exc.exception))
        self.assertEqual(side_effects, [])

    def test_direct_execution_scope_remains_compatible(self):
        target = "github.create_issue"
        action = ActionIntent(
            agent_id="tool-agent",
            action_type="mcp.tool.call",
            target=target,
            metadata={
                "arguments": {"title": "signed"},
                "execution_graph": {
                    "module": "enforcement.tool",
                    "hook": "ToolExecutionAdapter",
                    "router": "ExecutionRouter",
                    "target": target,
                    "enforcement_scope": "direct",
                },
            },
        )
        auth = self._auth(action)
        adapter = ToolExecutionAdapter(
            self.storage,
            self.public_key,
            {target: lambda _signed_action: "registered"},
        )
        router = ExecutionRouter(
            NetworkRegistry(),
            self.storage,
            self.public_key,
            generic_adapters={"mcp.tool.call": adapter},
        )
        self.assertEqual(router.execute(auth, lambda _signed_action: "sent"), "sent")

    def test_http_execution_uses_exact_signed_url_and_method(self):
        action = ActionIntent(
            agent_id="api-agent",
            action_type="api.request",
            target="https://api.example.test/v1/items",
            metadata={
                "method": "post",
                "url": "https://api.example.test/v1/items",
                "headers": {"x-verigate": "1"},
                "body": {"name": "signed"},
            },
        )
        auth = self._auth(action)
        requests = []
        adapter = HTTPExecutionAdapter(self.storage, self.public_key)
        result = adapter.execute_request(auth, lambda request: requests.append(request) or {"status": 201})
        self.assertEqual(result["status"], 201)
        self.assertEqual(requests[0]["method"], "POST")
        self.assertEqual(requests[0]["url"], action.target)
        self.assertEqual(requests[0]["body"], {"name": "signed"})

    def test_router_dispatches_generic_tool_action_to_fabric(self):
        action = ActionIntent(
            agent_id="router-agent",
            action_type="mcp.tool.call",
            target="github.create_issue",
            metadata={"arguments": {"title": "via-router"}},
        )
        auth = self._auth(action)
        calls = []
        adapter = ToolExecutionAdapter(
            self.storage,
            self.public_key,
            {"github.create_issue": lambda _signed_action: "registered"},
        )
        router = ExecutionRouter(
            NetworkRegistry(),
            self.storage,
            self.public_key,
            generic_adapters={"mcp.tool.call": adapter},
        )
        self.assertIs(router._adapter(auth), adapter)
        self.assertEqual(
            router.execute(auth, lambda signed_action: calls.append(signed_action) or "routed"),
            "routed",
        )
        self.assertEqual(calls[0]["metadata"]["arguments"]["title"], "via-router")

    def test_http_target_url_drift_fails_before_consumption(self):
        action = ActionIntent(
            agent_id="api-agent",
            action_type="api.request",
            target="https://api.example.test/v1/items",
            metadata={
                "method": "POST",
                "url": "https://attacker.example.test/steal",
            },
        )
        auth = self._auth(action)
        adapter = HTTPExecutionAdapter(self.storage, self.public_key)
        ok, reason = adapter.consume(auth)
        self.assertFalse(ok)
        self.assertIn("does not match signed URL", reason)


if __name__ == "__main__":
    unittest.main()
