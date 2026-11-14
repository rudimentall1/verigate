import subprocess
import sys
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
from enforcement.tool import ToolExecutionAdapter, _handler_fingerprint, build_tool_execution_graph


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
        handler = lambda signed_action: signed_action["metadata"]["arguments"]["title"]
        action = ActionIntent(
            agent_id="tool-agent",
            action_type="mcp.tool.call",
            target="github.create_issue",
            resource="repo:verigate",
            metadata={
                "arguments": {"title": "signed-title"},
                "execution_graph": build_tool_execution_graph("github.create_issue", handler),
            },
        )
        auth = self._auth(action)
        adapter = ToolExecutionAdapter(
            self.storage, self.public_key, {"github.create_issue": handler},
        )
        self.assertEqual(adapter.execute_registered(auth), "signed-title")
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
                    "enforcement_scope": "direct",
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
        with self.assertRaises(TypeError):
            adapter.handlers[target] = malicious_handler

        self.assertIs(adapter.handlers[target], trusted_handler)
        self.assertEqual(adapter.execute_registered(auth), "trusted")

    def test_registered_handler_defaults_drift_is_blocked_before_side_effect(self):
        def trusted_handler(_action, endpoint="https://api.internal.example"):
            return endpoint

        target = "http.fetch"
        action = ActionIntent(
            agent_id="tool-agent",
            action_type="mcp.tool.call",
            target=target,
            metadata={
                "arguments": {"url": "https://api.internal.example/records"},
                "execution_graph": {
                    "module": "enforcement.tool",
                    "hook": "ToolExecutionAdapter",
                    "router": "ExecutionRouter",
                    "target": target,
                    "enforcement_scope": "direct",
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

        trusted_handler.__defaults__ = ("https://attacker.example",)

        router = ExecutionRouter(
            NetworkRegistry(),
            self.storage,
            self.public_key,
            generic_adapters={"mcp.tool.call": adapter},
        )
        side_effects = []
        with self.assertRaises(ValueError) as exc:
            router.execute(auth, lambda signed_action: side_effects.append(signed_action) or "sent")
        self.assertIn("execution handler drift", str(exc.exception))
        self.assertEqual(side_effects, [])

    def test_transitive_execution_claim_is_rejected_by_direct_only_tool_adapter(self):
        target = "github.create_issue"
        def handler(_signed_action):
            raise AssertionError("handler must not run for transitive scope")

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


    def test_handler_fingerprint_is_stable_across_processes(self):
        script = """
from enforcement.tool import tool_handler_fingerprint

def stable_handler(action, endpoint="https://api.internal.example"):
    return endpoint

print(tool_handler_fingerprint(stable_handler))
"""
        repo_root = Path(__file__).resolve().parents[1]
        fingerprints = []
        for _ in range(2):
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            )
            fingerprints.append(result.stdout.strip())
        self.assertEqual(fingerprints[0], fingerprints[1])

    def test_mutable_and_custom_handler_defaults_are_rejected(self):
        def mutable_default(_action, cache=[]):
            return cache

        class UnstableDefault:
            pass

        marker = UnstableDefault()

        def custom_default(_action, value=marker):
            return value

        with self.assertRaisesRegex(ValueError, "immutable deterministic primitives"):
            build_tool_execution_graph("tool.mutable", mutable_default)
        with self.assertRaisesRegex(ValueError, "immutable deterministic primitives"):
            build_tool_execution_graph("tool.custom", custom_default)

    def test_keyword_handler_defaults_are_bound_and_mutable_values_rejected(self):
        def handler(_action, *, endpoint="https://api.internal.example"):
            return endpoint

        before = _handler_fingerprint(handler)
        handler.__kwdefaults__ = {"endpoint": "https://attacker.example"}
        after = _handler_fingerprint(handler)
        self.assertNotEqual(before, after)

        def mutable_keyword_default(_action, *, options=None):
            return options

        mutable_keyword_default.__kwdefaults__ = {"options": {"unsafe": True}}
        with self.assertRaisesRegex(ValueError, "immutable deterministic primitives"):
            build_tool_execution_graph("tool.keyword", mutable_keyword_default)

    def test_handler_fingerprint_binds_immutable_closure_values(self):
        def make_handler(endpoint):
            def handler(_action):
                return endpoint
            return handler

        first = make_handler("https://api.internal.example")
        same = make_handler("https://api.internal.example")
        changed = make_handler("https://attacker.example")
        self.assertEqual(_handler_fingerprint(first), _handler_fingerprint(same))
        self.assertNotEqual(_handler_fingerprint(first), _handler_fingerprint(changed))

    def test_mutable_handler_closure_is_rejected(self):
        def make_handler():
            calls = []
            def handler(_action):
                calls.append("called")
                return "ok"
            return handler

        with self.assertRaisesRegex(ValueError, "closure variable .*immutable"):
            build_tool_execution_graph("tool.mutable-closure", make_handler())

    def test_bound_method_handler_is_rejected(self):
        class StatefulHandler:
            def __init__(self):
                self.endpoint = "https://api.internal.example"

            def __call__(self, _action):
                return self.endpoint

        instance = StatefulHandler()
        with self.assertRaisesRegex(ValueError, "bound tool methods are not supported"):
            build_tool_execution_graph("http.fetch", instance.__call__)

    def test_registered_handler_mapping_is_immutable(self):
        handler = lambda _action: "registered"
        adapter = ToolExecutionAdapter(
            self.storage, self.public_key, {"github.create_issue": handler},
        )
        with self.assertRaises(TypeError):
            adapter.handlers["github.create_issue"] = lambda _action: "substituted"
        with self.assertRaises(AttributeError):
            adapter.handlers = {"github.create_issue": lambda _action: "substituted"}
        self.assertIs(adapter.handlers["github.create_issue"], handler)

    def test_direct_execution_scope_remains_compatible(self):
        target = "github.create_issue"
        handler = lambda _signed_action: "registered"
        action = ActionIntent(
            agent_id="tool-agent",
            action_type="mcp.tool.call",
            target=target,
            metadata={
                "arguments": {"title": "signed"},
                "execution_graph": build_tool_execution_graph(target, handler),
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
        handler = lambda _signed_action: "registered"
        action = ActionIntent(
            agent_id="router-agent",
            action_type="mcp.tool.call",
            target="github.create_issue",
            metadata={
                "arguments": {"title": "via-router"},
                "execution_graph": build_tool_execution_graph("github.create_issue", handler),
            },
        )
        auth = self._auth(action)
        adapter = ToolExecutionAdapter(
            self.storage, self.public_key, {"github.create_issue": handler},
        )
        router = ExecutionRouter(
            NetworkRegistry(),
            self.storage,
            self.public_key,
            generic_adapters={"mcp.tool.call": adapter},
        )
        self.assertIs(router._adapter(auth), adapter)
        self.assertEqual(router.execute(auth, lambda _signed_action: "routed"), "routed")

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
