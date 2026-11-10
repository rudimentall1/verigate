import base64
import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.receipt import verify_execution_receipt
from core.authorization import AuthorizationService
from core.models import ActionIntent, Capability, Decision, GuardrailDecision
from core.storage import Storage
from core.authority_state import DynamicAuthorityService
from core.policy import Policy
from enforcement.evm import EVMExecutionAdapter
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter
from enforcement.solana import SolanaExecutionAdapter


class ExecutionReceiptTest(unittest.TestCase):
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
            load_private_key(self.private),
        )

    def tearDown(self):
        self.storage.close()
        self.tmpdir.cleanup()

    def _authorization(self, network, metadata):
        intent = ActionIntent(
            agent_id="receipt-agent",
            action_type="token.transfer",
            target="merchant",
            asset="USDC",
            network=network,
            metadata=metadata,
        )
        decision = GuardrailDecision(
            intent_id=intent.intent_id,
            agent_id=intent.agent_id,
            decision=Decision.ALLOW,
            matched_rules=(),
        )
        capability = Capability(
            capability_id=f"cap-receipt-{intent.intent_id}",
            agent_id=intent.agent_id,
            allowed_actions=("token.transfer",),
            allowed_targets=("merchant",),
            allowed_networks=(network,),
            allowed_assets=("USDC",),
        )
        self.storage.register_capability(capability)
        authority = DynamicAuthorityService(self.storage).snapshot(
            intent.agent_id, capability.capability_id
        )
        policy = Policy()
        return AuthorizationService().issue(
            intent,
            decision,
            policy.digest,
            load_private_key(self.private),
            nonce=intent.intent_id,
            capability=capability,
            authority=authority,
            policy=policy,
        )["execution_authorization"]

    def test_success_receipt_binds_transaction_and_persists(self):
        auth = self._authorization(
            "base",
            {"evm_transaction": {"chain_id": 8453, "to": "0xMerchant", "value_wei": 0, "data": "0x"}},
        )
        receipt = self.router.execute_with_receipt(auth, lambda tx: "0xabc123")
        value = receipt.as_dict()
        self.assertEqual(value["payload"]["status"], "SUBMITTED")
        self.assertEqual(value["payload"]["transaction_ref"], "0xabc123")
        self.assertEqual(value["payload"]["authorization_id"], auth["payload"]["authorization_id"])
        self.assertTrue(verify_execution_receipt(value, load_public_key(self.public), auth)[0])
        stored = self.storage.execution_receipt_by_authorization(auth["payload"]["authorization_id"])
        self.assertEqual(stored["payload"]["receipt_id"], value["payload"]["receipt_id"])

    def test_failed_broadcast_produces_failed_receipt_and_consumes_capability(self):
        auth = self._authorization(
            "base",
            {"evm_transaction": {"chain_id": 8453, "to": "0xMerchant", "value_wei": 0, "data": "0x"}},
        )
        receipt = self.router.execute_with_receipt(
            auth,
            lambda tx: (_ for _ in ()).throw(RuntimeError("rpc offline")),
        )
        self.assertEqual(receipt.payload["status"], "FAILED")
        self.assertIn("rpc offline", receipt.payload["error"])
        self.assertTrue(verify_execution_receipt(receipt.as_dict(), load_public_key(self.public), auth)[0])
        second = self.router.execute_with_receipt(auth, lambda tx: "0xretry")
        self.assertEqual(second.payload["status"], "FAILED")
        self.assertEqual(second.as_dict(), receipt.as_dict())
        self.assertEqual(len(self.storage.execution_receipts("receipt-agent")), 1)

    def test_solana_receipt_uses_signature_reference(self):
        raw = base64.b64encode(b"signed-solana").decode("ascii")
        auth = self._authorization("solana", {"solana_transaction": raw})
        receipt = self.router.execute_with_receipt(auth, lambda tx: "5nSolSig")
        self.assertIsInstance(self.router._adapter(auth), SolanaExecutionAdapter)
        self.assertEqual(receipt.payload["transaction_ref"], "5nSolSig")
        self.assertEqual(receipt.payload["status"], "SUBMITTED")

    def test_tampering_receipt_fails_verification(self):
        auth = self._authorization(
            "base",
            {"evm_transaction": {"chain_id": 8453, "to": "0xMerchant", "value_wei": 0, "data": "0x"}},
        )
        receipt = self.router.execute_with_receipt(auth, lambda tx: "0xabc")
        value = receipt.as_dict()
        value["payload"]["transaction_ref"] = "0xevil"
        self.assertFalse(verify_execution_receipt(value, load_public_key(self.public))[0])


if __name__ == "__main__":
    unittest.main()
