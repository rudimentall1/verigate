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

    def test_authorization_binds_atomic_guard_state(self):
        storage = Storage(self.db)
        policy_path = Path(self.tmpdir.name) / "atomic-policy.yaml"
        policy_path.write_text("""allowed_networks: [arbitrum-sepolia]
allowed_assets: [USDC]
external_state_requirements:
  - action_type: payment
    target: merchant
    kind: evm.state
""", encoding="utf-8")
        engine = GuardrailEngine(Policy.load(policy_path), storage)
        guard = "0x" + "11" * 20
        oracle = "0x" + "22" * 20
        reference = "0x" + "33" * 32
        expected = "0x" + "44" * 32
        tx = {"chain_id": 421614, "to": guard, "value_wei": 0, "data": "0x1234"}
        import hashlib, json
        data_sha256 = hashlib.sha256(tx["data"].encode("utf-8")).hexdigest()
        state = {
            "kind": "evm.state",
            "reference": "resource:merchant",
            "digest": "a" * 64,
            "atomic_guard": {
                "address": guard, "oracle": oracle, "reference": reference,
                "expected": expected, "data_sha256": data_sha256,
            },
        }
        intent = PaymentIntent(
            agent_id="agent-evm", payee="merchant", asset="USDC", network="arbitrum-sepolia", amount=1.0,
            metadata={"evm_transaction": tx, "external_state": state},
        )
        capability = Capability(
            capability_id="cap-atomic", agent_id="agent-evm", allowed_actions=("payment",),
            allowed_targets=("merchant",), allowed_networks=("arbitrum-sepolia",),
            allowed_assets=("USDC",), max_per_action={"USDC": 10.0},
        )
        storage.register_capability(capability)
        result = engine.authorize_with_capability(intent, capability.capability_id, load_private_key(self.priv))
        auth = result["execution_authorization"]
        self.assertIsNotNone(auth)
        self.assertEqual(auth["payload"]["external_state"]["kind"], "evm.state")
        self.assertEqual(auth["payload"]["external_state"]["atomic_guard"]["address"], guard)
        self.assertEqual(auth["payload"]["external_state_requirement"]["kind"], "evm.state")
        storage.close()

    def test_router_requires_atomic_guard_for_policy_bound_evm_state(self):
        storage = Storage(self.db)
        policy_path = Path(self.tmpdir.name) / "atomic-router-policy.yaml"
        policy_path.write_text("""allowed_networks: [arbitrum-sepolia]
allowed_assets: [USDC]
external_state_requirements:
  - action_type: payment
    target: merchant
    kind: evm.state
""", encoding="utf-8")
        engine = GuardrailEngine(Policy.load(policy_path), storage)
        tx = {"chain_id": 421614, "to": "0x" + "11" * 20, "value_wei": 0, "data": "0x1234"}
        state = {"kind": "evm.state", "reference": "resource:merchant", "digest": "a" * 64}
        intent = PaymentIntent(agent_id="agent-evm", payee="merchant", asset="USDC", network="arbitrum-sepolia", amount=1.0, metadata={"evm_transaction": tx, "external_state": state})
        capability = Capability(capability_id="cap-atomic-router", agent_id="agent-evm", allowed_actions=("payment",), allowed_targets=("merchant",), allowed_networks=("arbitrum-sepolia",), allowed_assets=("USDC",), max_per_action={"USDC": 10.0})
        storage.register_capability(capability)
        result = engine.authorize_with_capability(intent, capability.capability_id, load_private_key(self.priv))
        from enforcement.router import ExecutionRouter
        from enforcement.networks import NetworkRegistry
        router = ExecutionRouter(NetworkRegistry(), storage, load_public_key(self.pub))
        calls=[]
        with self.assertRaises(ValueError):
            router.execute(result["execution_authorization"], lambda value: calls.append(value) or "tx")
        self.assertEqual(calls, [])
        storage.close()

    def test_control_plane_router_atomic_execution_with_receipt(self):
        from enforcement.router import ExecutionRouter
        from enforcement.networks import NetworkRegistry
        from core.external_state import ExternalStateVerifierRegistry
        import hashlib, json

        storage = Storage(self.db)
        policy_path = Path(self.tmpdir.name) / "control-plane-policy.yaml"
        policy_path.write_text("""allowed_networks: [arbitrum-sepolia]
allowed_assets: [USDC]
external_state_requirements:
  - action_type: payment
    target: merchant
    kind: evm.state
""", encoding="utf-8")
        engine = GuardrailEngine(Policy.load(policy_path), storage)
        guard = "0x" + "11" * 20
        oracle = "0x" + "22" * 20
        reference = "0x" + "33" * 32
        expected = "0x" + "44" * 32
        data = "0x1234"
        observation = {"kind":"evm.state","chain_id":421614,"address":oracle.lower(),"block_tag":"latest","code":"0x6000","storage":{"0x"+"00"*32:"0x"+"44"*32}}
        state_digest = hashlib.sha256(json.dumps(observation, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        state = {"kind":"evm.state","reference":"oracle:live","digest":state_digest,"chain_id":421614,"address":oracle,"block_tag":"latest","storage_slots":["0x"+"00"*32],"atomic_guard":{"address":guard,"oracle":oracle,"reference":reference,"expected":expected,"data_sha256":hashlib.sha256(data.encode()).hexdigest()}}
        tx = {"chain_id":421614,"to":guard,"value_wei":0,"data":data}
        intent = PaymentIntent(agent_id="agent-evm", payee="merchant", asset="USDC", network="arbitrum-sepolia", amount=1.0, metadata={"evm_transaction":tx,"external_state":state,"network_family":"evm"})
        capability = Capability(capability_id="cap-control-plane", agent_id="agent-evm", allowed_actions=("payment",), allowed_targets=("merchant",), allowed_networks=("arbitrum-sepolia",), allowed_assets=("USDC",), max_per_action={"USDC":10.0})
        storage.register_capability(capability)
        result = engine.authorize_with_capability(intent, capability.capability_id, load_private_key(self.priv))
        auth = result["execution_authorization"]
        self.assertIsNotNone(auth)

        class LiveVerifier:
            def __call__(self, binding, action):
                return True, "live state matches"

        registry = ExternalStateVerifierRegistry({"evm.state": LiveVerifier()})
        router = ExecutionRouter(NetworkRegistry(), storage, load_public_key(self.pub), private_key=load_private_key(self.priv), external_state_registry=registry)
        calls=[]
        receipt = router.execute_with_receipt(auth, lambda value: calls.append(value) or "0xlive-tx")
        self.assertEqual(receipt.payload["status"], "SUBMITTED", receipt.payload.get("error"))
        self.assertEqual(receipt.payload["transaction_ref"], "0xlive-tx")
        self.assertEqual(calls, [tx])
        self.assertIsNotNone(storage.execution_receipt_by_authorization(auth["payload"]["authorization_id"]))
        storage.close()

    def test_stale_authorization_is_blocked_after_external_state_drift(self):
        from enforcement.router import ExecutionRouter
        from enforcement.networks import NetworkRegistry
        from core.external_state import ExternalStateVerifierRegistry
        import hashlib, json

        storage = Storage(self.db)
        policy_path = Path(self.tmpdir.name) / "stale-state-policy.yaml"
        policy_path.write_text("""allowed_networks: [arbitrum-sepolia]
allowed_assets: [USDC]
external_state_requirements:
  - action_type: payment
    target: merchant
    kind: evm.state
""", encoding="utf-8")
        engine = GuardrailEngine(Policy.load(policy_path), storage)
        guard = "0x" + "11" * 20
        oracle = "0x" + "22" * 20
        reference = "0x" + "33" * 32
        expected = "0x" + "44" * 32
        data = "0x1234"
        observation = {"kind":"evm.state","chain_id":421614,"address":oracle.lower(),"block_tag":"latest","code":"0x6000","storage":{"0x"+"00"*32:"0x"+"44"*32}}
        state_digest = hashlib.sha256(json.dumps(observation, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        state = {"kind":"evm.state","reference":"oracle:live","digest":state_digest,"chain_id":421614,"address":oracle,"block_tag":"latest","storage_slots":["0x"+"00"*32],"atomic_guard":{"address":guard,"oracle":oracle,"reference":reference,"expected":expected,"data_sha256":hashlib.sha256(data.encode()).hexdigest()}}
        tx = {"chain_id":421614,"to":guard,"value_wei":0,"data":data}
        intent = PaymentIntent(agent_id="agent-evm", payee="merchant", asset="USDC", network="arbitrum-sepolia", amount=1.0, metadata={"evm_transaction":tx,"external_state":state,"network_family":"evm"})
        capability = Capability(capability_id="cap-stale-state", agent_id="agent-evm", allowed_actions=("payment",), allowed_targets=("merchant",), allowed_networks=("arbitrum-sepolia",), allowed_assets=("USDC",), max_per_action={"USDC":10.0})
        storage.register_capability(capability)
        result = engine.authorize_with_capability(intent, capability.capability_id, load_private_key(self.priv))
        auth = result["execution_authorization"]
        self.assertIsNotNone(auth)

        drifted = {"value": False}
        class LiveVerifier:
            def __call__(self, binding, action):
                if drifted["value"]:
                    return False, "oracle state changed after authorization"
                return True, "live state matches"

        registry = ExternalStateVerifierRegistry({"evm.state": LiveVerifier()})
        router = ExecutionRouter(NetworkRegistry(), storage, load_public_key(self.pub), private_key=load_private_key(self.priv), external_state_registry=registry)
        calls = []
        drifted["value"] = True
        receipt = router.execute_with_receipt(auth, lambda value: calls.append(value) or "0xmust-not-broadcast")

        self.assertEqual(receipt.payload["status"], "FAILED")
        self.assertIn("external state drift", receipt.payload["error"])
        self.assertEqual(calls, [])
        self.assertIsNone(receipt.payload["transaction_ref"])
        storage.close()

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



