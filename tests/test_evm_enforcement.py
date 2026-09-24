import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.engine import GuardrailEngine
from core.models import Capability, PaymentIntent
from core.policy import Policy
from core.authority_state import DynamicAuthorityService
from core.storage import Storage
from enforcement.evm import EVMExecutionAdapter
from enforcement.protocol import ExecutionAdapter


class EVMExecutionAdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.priv = Path(self.tmpdir.name) / "issuer.key"
        self.pub = Path(self.tmpdir.name) / "issuer.pub"
        self.db = Path(self.tmpdir.name) / "audit.db"
        self.policy = Path(self.tmpdir.name) / "policy.yaml"
        self.policy.write_text("allowed_networks: [base]\nallowed_assets: [USDC]\n", encoding="utf-8")
        generate_keypair(self.priv, self.pub)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _authorized(self):
        storage = Storage(self.db)
        engine = GuardrailEngine(Policy.load(self.policy), storage)
        tx = {"chain_id": 8453, "to": "0xabc", "value_wei": 0, "data": "0xa9059cbb"}
        intent = PaymentIntent(
            agent_id="agent-evm", payee="merchant", asset="USDC", network="base", amount=1.0,
            metadata={"evm_transaction": tx},
        )
        capability = Capability(
            capability_id="cap-evm-test",
            agent_id="agent-evm",
            allowed_actions=("payment",),
            allowed_targets=("merchant",),
            allowed_networks=("base",),
            allowed_assets=("USDC",),
            max_per_action={"USDC": 10.0},
        )
        storage.register_capability(capability)
        result = engine.authorize_with_capability(
            intent, capability.capability_id, load_private_key(self.priv)
        )
        storage.close()
        return result, tx

    def test_adapter_implements_shared_boundary(self):
        result, _ = self._authorized()
        adapter = EVMExecutionAdapter(Storage(self.db), load_public_key(self.pub))
        try:
            self.assertIsInstance(adapter, ExecutionAdapter)
            ok, reason = adapter.consume(result["execution_authorization"])
            self.assertTrue(ok, reason)
        finally:
            adapter.gate.storage.close()

    def test_broadcast_receives_signed_transaction_envelope(self):
        result, tx = self._authorized()
        adapter = EVMExecutionAdapter(Storage(self.db), load_public_key(self.pub))
        calls = []
        try:
            receipt = adapter.execute(result["execution_authorization"], lambda value: calls.append(value) or "tx-hash")
            self.assertEqual(receipt, "tx-hash")
            self.assertEqual(calls, [tx])
        finally:
            adapter.gate.storage.close()

    def test_action_tampering_blocks_before_broadcast(self):
        result, _ = self._authorized()
        adapter = EVMExecutionAdapter(Storage(self.db), load_public_key(self.pub))
        calls = []
        try:
            result["execution_authorization"]["payload"]["action"]["metadata"]["evm_transaction"]["to"] = "0xattacker"
            with self.assertRaises(PermissionError):
                adapter.execute(result["execution_authorization"], lambda value: calls.append(value))
            self.assertEqual(calls, [])
        finally:
            adapter.gate.storage.close()

    def test_execute_bound_requires_atomic_guard_binding(self):
        result, tx = self._authorized()
        adapter = EVMExecutionAdapter(Storage(self.db), load_public_key(self.pub))
        try:
            auth = result["execution_authorization"]
            state = {"kind": "evm.state", "atomic_guard": {}}
            with self.assertRaises(ValueError):
                adapter.execute_bound(auth, state, lambda value: "tx-hash")
        finally:
            adapter.gate.storage.close()

    def test_execute_bound_requires_guard_target(self):
        result, _ = self._authorized()
        adapter = EVMExecutionAdapter(Storage(self.db), load_public_key(self.pub))
        try:
            auth = result["execution_authorization"]
            state = {"kind": "evm.state", "atomic_guard": {
                "address": "0xGuard",
                "oracle": "0xOracle",
                "reference": "0x" + "11" * 32,
                "expected": "0x" + "22" * 32,
                "data_sha256": "0" * 64,
            }}
            with self.assertRaises(ValueError):
                adapter.execute_bound(auth, state, lambda value: "tx-hash")
        finally:
            adapter.gate.storage.close()

    def test_replay_does_not_broadcast_twice(self):
        result, _ = self._authorized()
        adapter = EVMExecutionAdapter(Storage(self.db), load_public_key(self.pub))
        calls = []
        try:
            adapter.execute(result["execution_authorization"], lambda value: calls.append(value) or "first")
            with self.assertRaises(PermissionError):
                adapter.execute(result["execution_authorization"], lambda value: calls.append(value) or "second")
            self.assertEqual(len(calls), 1)
        finally:
            adapter.gate.storage.close()


if __name__ == "__main__":
    unittest.main()
