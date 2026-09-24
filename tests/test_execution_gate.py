import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.receipt import issue_execution_authorization
from core.engine import GuardrailEngine
from core.policy import Policy
from core.storage import Storage
from core.models import Capability, PaymentIntent
from enforcement.local import ExecutionGate
from enforcement.protocol import ExecutionAdapter


class ExecutionGateTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.priv = Path(self.tmpdir.name) / "issuer.key"
        self.pub = Path(self.tmpdir.name) / "issuer.pub"
        self.db = Path(self.tmpdir.name) / "audit.db"
        generate_keypair(self.priv, self.pub)
        self.policy_path = Path(self.tmpdir.name) / "policy.yaml"
        self.policy_path.write_text(
            "allowed_networks: [base]\nallowed_assets: [USDC]\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def _authorization(self):
        storage = Storage(self.db)
        engine = GuardrailEngine(Policy.load(self.policy_path), storage)
        intent = PaymentIntent(
            agent_id="agent-1", payee="merchant", asset="USDC",
            network="base", amount=1.0,
        )
        capability = Capability(
            capability_id="cap-gate-test",
            agent_id=intent.agent_id,
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
        return result

    def _auth_pair(self):
        result = self._authorization()
        return (
            result["execution_authorization"],
            result["decision_receipt"]["payload"]["intent"],
        )

    def test_local_gate_implements_execution_adapter_boundary(self):
        auth, action = self._auth_pair()
        storage = Storage(self.db)
        try:
            gate = ExecutionGate(storage, load_public_key(self.pub))
            self.assertIsInstance(gate, ExecutionAdapter)
            ok, reason = gate.consume(auth)
            self.assertTrue(ok, reason)
        finally:
            storage.close()

    def test_authorization_is_consumed_only_once(self):
        auth, action = self._auth_pair()
        storage = Storage(self.db)
        try:
            gate = ExecutionGate(storage, load_public_key(self.pub))
            ok, reason = gate.consume(auth)
            self.assertTrue(ok, reason)
            ok, reason = gate.consume(auth)
            self.assertFalse(ok)
            self.assertEqual(reason, "execution authorization already consumed")
        finally:
            storage.close()

    def test_concurrent_workers_can_consume_authorization_only_once(self):
        auth, action = self._auth_pair()
        storage_a = Storage(self.db)
        storage_b = Storage(self.db)
        try:
            gate_a = ExecutionGate(storage_a, load_public_key(self.pub))
            gate_b = ExecutionGate(storage_b, load_public_key(self.pub))
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda gate: gate.consume(auth), (gate_a, gate_b)))
            self.assertEqual(sum(ok for ok, _ in results), 1)
            self.assertEqual(sum(reason == "execution authorization already consumed" for _, reason in results), 1)
        finally:
            storage_a.close()
            storage_b.close()

    def test_replay_is_rejected_after_storage_reopen(self):
        auth, action = self._auth_pair()
        storage = Storage(self.db)
        gate = ExecutionGate(storage, load_public_key(self.pub))
        ok, reason = gate.consume(auth)
        self.assertTrue(ok, reason)
        storage.close()

        storage = Storage(self.db)
        try:
            gate = ExecutionGate(storage, load_public_key(self.pub))
            ok, reason = gate.consume(auth)
            self.assertFalse(ok)
            self.assertEqual(reason, "execution authorization already consumed")
        finally:
            storage.close()

    def test_tampered_authorization_is_rejected(self):
        auth, action = self._auth_pair()
        auth["payload"]["intent_id"] = "attacker-intent"
        storage = Storage(self.db)
        try:
            gate = ExecutionGate(storage, load_public_key(self.pub))
            ok, reason = gate.consume(auth)
            self.assertFalse(ok)
            self.assertEqual(reason, "authorized action identity mismatch")
        finally:
            storage.close()


    def test_execute_reaches_side_effect_once(self):
        auth, action = self._auth_pair()
        calls = []
        storage = Storage(self.db)
        try:
            gate = ExecutionGate(storage, load_public_key(self.pub))
            result = gate.execute(auth, lambda _: calls.append("executed") or "ok")
            self.assertEqual(result, "ok")
            self.assertEqual(calls, ["executed"])
            with self.assertRaises(PermissionError):
                gate.execute(auth, lambda _: calls.append("replayed"))
            self.assertEqual(calls, ["executed"])
        finally:
            storage.close()

    def test_block_has_no_execution_authorization(self):
        policy_path = Path(self.tmpdir.name) / "block-policy.yaml"
        policy_path.write_text(
            "allowed_networks: [base]\nallowed_assets: [USDC]\nblocked_payees: [evil]\n",
            encoding="utf-8",
        )
        storage = Storage(self.db)
        try:
            engine = GuardrailEngine(Policy.load(policy_path), storage)
            result = engine.authorize(
                PaymentIntent(
                    agent_id="agent-1", payee="evil", asset="USDC",
                    network="base", amount=1.0,
                ),
                load_private_key(self.priv),
            )
            self.assertEqual(result["decision_receipt"]["payload"]["decision"]["decision"], "BLOCK")
            self.assertIsNone(result["execution_authorization"])
        finally:
            storage.close()

    def test_expired_authorization_is_rejected(self):
        result = self._authorization()
        receipt = result["decision_receipt"]
        valid = result["execution_authorization"]
        expired = issue_execution_authorization(
            type("Receipt", (), {
                "payload": receipt["payload"],
                "signature": receipt["signature"],
            })(),
            load_private_key(self.priv),
            nonce=receipt["payload"]["intent"]["intent_id"],
            ttl_seconds=-1,
            capability_id=valid["payload"]["capability_id"],
            capability_version=valid["payload"]["capability_version"],
            capability_sha256=valid["payload"]["capability_sha256"],
            authority_state=valid["payload"]["authority_state"],
            authority_state_sha256=valid["payload"]["authority_state_sha256"],
            authority_multiplier=valid["payload"]["authority_multiplier"],
            effective_authority=valid["payload"]["effective_authority"],
        ).as_dict()
        storage = Storage(self.db)
        try:
            gate = ExecutionGate(storage, load_public_key(self.pub))
            ok, reason = gate.consume(expired)
            self.assertFalse(ok)
            self.assertEqual(reason, "execution authorization expired")
        finally:
            storage.close()



    def test_real_file_side_effect_is_gated(self):
        auth, action = self._auth_pair()
        target = Path(self.tmpdir.name) / "authorized-side-effect.txt"
        storage = Storage(self.db)
        try:
            gate = ExecutionGate(storage, load_public_key(self.pub))
            gate.execute(auth, lambda _: target.write_text("AUTHORIZED\n", encoding="utf-8"))
            self.assertEqual(target.read_text(encoding="utf-8"), "AUTHORIZED\n")
            with self.assertRaises(PermissionError):
                gate.execute(auth, lambda _: target.write_text("REPLAYED\n", encoding="utf-8"))
            self.assertEqual(target.read_text(encoding="utf-8"), "AUTHORIZED\n")
        finally:
            storage.close()

if __name__ == "__main__":
    unittest.main()
