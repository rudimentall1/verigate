import copy
import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authorization import AuthorizationService
from core.models import ActionIntent, Decision, GuardrailDecision
from core.storage import Storage
from enforcement.router import ExecutionRouter
from enforcement.networks import NetworkRegistry


class TamperEnforcementTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.private = root / "issuer.key"
        self.public = root / "issuer.pub"
        self.db = root / "audit.db"
        generate_keypair(self.private, self.public)
        self.storage = Storage(self.db)
        self.router = ExecutionRouter(
            NetworkRegistry(),
            self.storage,
            load_public_key(self.public),
        )

    def tearDown(self):
        self.storage.close()
        self.tmpdir.cleanup()

    def _authorization(self):
        intent = ActionIntent(
            agent_id="tamper-agent",
            action_type="tool.execute",
            target="approved-merchant",
            resource="https://api.approved.example/pay",
            amount=500.0,
            asset="USDC",
            network="base",
            metadata={
                "tool_endpoint": "https://api.approved.example/pay",
                "evm_transaction": {
                    "chain_id": 8453,
                    "to": "0xApproved",
                    "value_wei": 500_000_000,
                    "data": "0x1234",
                },
            },
        )
        decision = GuardrailDecision(
            intent_id=intent.intent_id,
            agent_id=intent.agent_id,
            decision=Decision.ALLOW,
            matched_rules=(),
        )
        return AuthorizationService().issue(
            intent,
            decision,
            "tamper-test-policy",
            load_private_key(self.private),
            nonce=intent.intent_id,
        )["execution_authorization"]

    def _assert_mutation_is_blocked(self, mutate):
        authorization = self._authorization()
        mutate(authorization)
        calls = []
        with self.assertRaises((PermissionError, ValueError)):
            self.router.execute(
                  authorization,
                lambda tx: calls.append(tx) or "should-not-broadcast",
            )
        self.assertEqual(calls, [])

    def test_changed_tool_endpoint_is_blocked(self):
        def mutate(auth):
            action = auth["payload"]["action"]
            action["metadata"]["tool_endpoint"] = "https://attacker.example/collect"

        self._assert_mutation_is_blocked(mutate)

    def test_changed_destination_is_blocked(self):
        def mutate(auth):
            action = auth["payload"]["action"]
            action["metadata"]["evm_transaction"]["to"] = "0xAttacker"

        self._assert_mutation_is_blocked(mutate)

    def test_changed_amount_is_blocked(self):
        def mutate(auth):
            action = auth["payload"]["action"]
            action["metadata"]["evm_transaction"]["value_wei"] = 9_999_000_000

        self._assert_mutation_is_blocked(mutate)

    def test_changed_calldata_is_blocked(self):
        def mutate(auth):
            action = auth["payload"]["action"]
            action["metadata"]["evm_transaction"]["data"] = "0xdeadbeef"

        self._assert_mutation_is_blocked(mutate)

    def test_changed_network_context_is_blocked(self):
        def mutate(auth):
            auth["payload"]["action"]["network"] = "arbitrum"

        self._assert_mutation_is_blocked(mutate)

    def test_changed_action_target_is_blocked(self):
        def mutate(auth):
            auth["payload"]["action"]["target"] = "attacker"

        self._assert_mutation_is_blocked(mutate)

    def test_changed_chain_id_is_blocked_before_broadcast(self):
        authorization = self._authorization()
        authorization = copy.deepcopy(authorization)
        authorization["payload"]["action"]["metadata"]["evm_transaction"]["chain_id"] = 1
        calls = []
        with self.assertRaises(ValueError):
            self.router.execute(
                authorization,
                lambda tx: calls.append(tx) or "should-not-broadcast",
            )
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
