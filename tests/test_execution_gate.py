import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.receipt import issue_execution_authorization
from core.engine import GuardrailEngine
from core.policy import Policy
from core.storage import Storage
from core.models import PaymentIntent
from enforcement.local import ExecutionGate


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
        result = engine.authorize(intent, load_private_key(self.priv))
        storage.close()
        return result

    def test_authorization_is_consumed_only_once(self):
        auth = self._authorization()["execution_authorization"]
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

    def test_replay_is_rejected_after_storage_reopen(self):
        auth = self._authorization()["execution_authorization"]
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
        auth = self._authorization()["execution_authorization"]
        auth["payload"]["intent_id"] = "attacker-intent"
        storage = Storage(self.db)
        try:
            gate = ExecutionGate(storage, load_public_key(self.pub))
            ok, reason = gate.consume(auth)
            self.assertFalse(ok)
            self.assertIn("invalid or tampered", reason)
        finally:
            storage.close()


    def test_execute_reaches_side_effect_once(self):
        auth = self._authorization()["execution_authorization"]
        calls = []
        storage = Storage(self.db)
        try:
            gate = ExecutionGate(storage, load_public_key(self.pub))
            result = gate.execute(auth, lambda: calls.append("executed") or "ok")
            self.assertEqual(result, "ok")
            self.assertEqual(calls, ["executed"])
            with self.assertRaises(PermissionError):
                gate.execute(auth, lambda: calls.append("replayed"))
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
        expired = issue_execution_authorization(
            type("Receipt", (), {
                "payload": receipt["payload"],
                "signature": receipt["signature"],
            })(),
            load_private_key(self.priv),
            nonce=receipt["payload"]["intent"]["intent_id"],
            ttl_seconds=-1,
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
        auth = self._authorization()["execution_authorization"]
        target = Path(self.tmpdir.name) / "authorized-side-effect.txt"
        storage = Storage(self.db)
        try:
            gate = ExecutionGate(storage, load_public_key(self.pub))
            gate.execute(auth, lambda: target.write_text("AUTHORIZED\n", encoding="utf-8"))
            self.assertEqual(target.read_text(encoding="utf-8"), "AUTHORIZED\n")
            with self.assertRaises(PermissionError):
                gate.execute(auth, lambda: target.write_text("REPLAYED\n", encoding="utf-8"))
            self.assertEqual(target.read_text(encoding="utf-8"), "AUTHORIZED\n")
        finally:
            storage.close()

if __name__ == "__main__":
    unittest.main()
