import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.receipt import sign_receipt, verify_receipt
from core.models import ActionIntent, Decision, GuardrailDecision, PaymentIntent
from core.engine import GuardrailEngine
from core.policy import Policy
from core.storage import Storage


class AuthorizationReceiptTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.priv = Path(self.tmpdir.name) / "issuer.key"
        self.pub = Path(self.tmpdir.name) / "issuer.pub"
        generate_keypair(self.priv, self.pub)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _receipt(self):
        intent = ActionIntent(
            agent_id="agent-1",
            action_type="http.request",
            target="api.example.com",
            resource="https://api.example.com/data",
            metadata={"method": "GET", "scope": "read:data"},
        )
        decision = GuardrailDecision(
            intent_id=intent.intent_id,
            agent_id=intent.agent_id,
            decision=Decision.ALLOW,
            matched_rules=(),
        )
        return sign_receipt(intent, decision, "a" * 64, load_private_key(self.priv))

    def test_receipt_binds_intent_decision_and_policy(self):
        payload = self._receipt().as_dict()["payload"]
        self.assertEqual(payload["receipt_version"], 1)
        self.assertEqual(payload["policy_sha256"], "a" * 64)
        self.assertEqual(payload["intent"]["action_type"], "http.request")
        self.assertEqual(payload["decision"]["decision"], "ALLOW")

    def test_receipt_verifies_offline(self):
        receipt = self._receipt().as_dict()
        ok, reason = verify_receipt(receipt, load_public_key(self.pub))
        self.assertTrue(ok, reason)


    def test_engine_authorize_produces_and_persists_receipt(self):
        policy_path = Path(self.tmpdir.name) / "policy.yaml"
        policy_path.write_text("allowed_networks: [base]\nallowed_assets: [USDC]\n", encoding="utf-8")
        policy = Policy.load(policy_path)
        storage = Storage(Path(self.tmpdir.name) / "audit.db")
        try:
            engine = GuardrailEngine(policy, storage)
            intent = PaymentIntent(
                agent_id="agent-1", payee="merchant", asset="USDC",
                network="base", amount=10.0,
            )
            receipt = engine.authorize(intent, load_private_key(self.priv))
            data = receipt.as_dict()
            self.assertEqual(data["payload"]["intent"]["action_type"], "payment")
            self.assertEqual(data["payload"]["policy_sha256"], policy.digest)
            self.assertEqual(storage.count_intent(intent.intent_id), 1)
            row = storage._conn.execute(
                "SELECT signature FROM audit_log WHERE intent_id = ?", (intent.intent_id,)
            ).fetchone()
            self.assertEqual(row[0], receipt.signature)
        finally:
            storage.close()

    def test_signing_failure_keeps_audit_record(self):
        policy_path = Path(self.tmpdir.name) / "policy.yaml"
        policy_path.write_text("allowed_networks: [base]\nallowed_assets: [USDC]\n", encoding="utf-8")
        storage = Storage(Path(self.tmpdir.name) / "audit-failure.db")
        try:
            engine = GuardrailEngine(Policy.load(policy_path), storage)
            intent = PaymentIntent(
                agent_id="agent-1", payee="merchant", asset="USDC",
                network="base", amount=1.0,
            )
            class FailingKey:
                def sign(self, data):
                    raise RuntimeError("boom")
            with self.assertRaises(RuntimeError):
                engine.authorize(intent, FailingKey())
            self.assertEqual(storage.count_intent(intent.intent_id), 1)
            row = storage._conn.execute(
                "SELECT signature FROM audit_log WHERE intent_id = ?", (intent.intent_id,)
            ).fetchone()
            self.assertIsNone(row[0])
        finally:
            storage.close()

    def test_tampering_policy_fingerprint_fails(self):
        receipt = self._receipt().as_dict()
        receipt["payload"]["policy_sha256"] = "b" * 64
        ok, _ = verify_receipt(receipt, load_public_key(self.pub))
        self.assertFalse(ok)

    def test_tampering_intent_fails(self):
        receipt = self._receipt().as_dict()
        receipt["payload"]["intent"]["target"] = "evil.example.com"
        ok, _ = verify_receipt(receipt, load_public_key(self.pub))
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
