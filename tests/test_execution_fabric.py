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
from enforcement.tool import ToolExecutionAdapter


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
