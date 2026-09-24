import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authorization import AuthorizationService
from core.authority_state import DynamicAuthorityService
from core.models import ActionIntent, Capability, GuardrailDecision, Decision
from core.policy import Policy
from core.storage import Storage
from enforcement.router import ExecutionRouter
from enforcement.networks import NetworkRegistry


class RecordingAdapter:
    def __init__(self):
        self.calls = 0

    def consume(self, authorization):
        self.calls += 1
        return True, "consumed"

    def execute(self, authorization, side_effect):
        self.calls += 1
        return side_effect(authorization["payload"]["action"])


class MaliciousAdapter(RecordingAdapter):
    pass


class ExecutionGraphEnforcementTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.private = root / "issuer.key"
        self.public = root / "issuer.pub"
        generate_keypair(self.private, self.public)
        self.storage = Storage(root / "audit.db")

    def tearDown(self):
        self.storage.close()
        self.tmpdir.cleanup()

    def _auth(self, action):
        capability = Capability(
            capability_id="cap-graph",
            agent_id=action.agent_id,
            allowed_actions=(action.action_type,),
            allowed_targets=(action.target,),
        )
        self.storage.register_capability(capability)
        authority = DynamicAuthorityService(self.storage).snapshot(
            action.agent_id, capability.capability_id
        )
        decision = GuardrailDecision(
            intent_id=action.intent_id,
            agent_id=action.agent_id,
            decision=Decision.ALLOW,
            matched_rules=(),
        )
        return AuthorizationService().issue(
            action, decision, Policy().digest, load_private_key(self.private),
            nonce=action.intent_id, capability=capability, authority=authority,
            policy=Policy(),
        )["execution_authorization"]

    def _action(self):
        return ActionIntent(
            agent_id="graph-agent",
            action_type="orders.create",
            target="orders.create",
            metadata={
                "execution_graph": {
                    "module": __name__,
                    "hook": "RecordingAdapter",
                    "router": "ExecutionRouter",
                    "target": "orders.create",
                }
            },
        )

    def test_matching_actual_path_executes(self):
        adapter = RecordingAdapter()
        router = ExecutionRouter(
            NetworkRegistry(), self.storage, load_public_key(self.public),
            generic_adapters={"orders.create": adapter},
        )
        auth = self._auth(self._action())
        sent = []
        result = router.execute(auth, lambda action: sent.append(action) or "ok")
        self.assertEqual(result, "ok")
        self.assertEqual(adapter.calls, 1)
        self.assertEqual(len(sent), 1)

    def test_generic_adapter_path_drift_is_blocked_before_side_effect(self):
        adapter = MaliciousAdapter()
        router = ExecutionRouter(
            NetworkRegistry(), self.storage, load_public_key(self.public),
            generic_adapters={"orders.create": adapter},
        )
        auth = self._auth(self._action())
        sent = []
        with self.assertRaises(ValueError):
            router.execute(auth, lambda action: sent.append(action) or "bad")
        self.assertEqual(adapter.calls, 0)
        self.assertEqual(sent, [])

    def test_consume_blocks_adapter_drift(self):
        adapter = MaliciousAdapter()
        router = ExecutionRouter(
            NetworkRegistry(), self.storage, load_public_key(self.public),
            generic_adapters={"orders.create": adapter},
        )
        auth = self._auth(self._action())
        ok, reason = router.consume(auth)
        self.assertFalse(ok)
        self.assertIn("execution graph drift: hook", reason)
        self.assertEqual(adapter.calls, 0)


if __name__ == "__main__":
    unittest.main()
