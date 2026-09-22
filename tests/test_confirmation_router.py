import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authorization import AuthorizationService
from core.models import ActionIntent, Decision, GuardrailDecision
from core.storage import Storage
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter
from attest.receipt import verify_execution_receipt


class ConfirmationRouterTest(unittest.TestCase):
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

    def _auth(self):
        intent = ActionIntent(
            agent_id="confirm-agent",
            action_type="token.transfer",
            target="merchant",
            asset="USDC",
            network="base",
            metadata={
                "evm_transaction": {
                    "chain_id": 8453,
                    "to": "0xMerchant",
                    "value_wei": 0,
                    "data": "0x",
                }
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
            "confirmation-policy",
            load_private_key(self.private),
            nonce=intent.intent_id,
        )["execution_authorization"]

    def test_pending_confirmation_keeps_submitted_receipt(self):
        auth = self._auth()
        submitted = self.router.execute_with_receipt(auth, lambda tx: "0xabc")
        result = self.router.confirm_execution_receipt(
            submitted.as_dict(),
            {"state": "PENDING", "transaction_ref": "0xabc"},
        )
        self.assertIsNone(result)
        stored = self.storage.execution_receipt_by_authorization(auth["payload"]["authorization_id"])
        self.assertEqual(stored["payload"]["status"], "SUBMITTED")

    def test_confirmed_updates_and_links_receipt(self):
        auth = self._auth()
        submitted = self.router.execute_with_receipt(auth, lambda tx: "0xabc")
        confirmed = self.router.confirm_execution_receipt(
            submitted.as_dict(),
            {
                "state": "CONFIRMED",
                "transaction_ref": "0xabc",
                "block_ref": "0x99",
                "block_hash": "0xblock",
            },
        )
        self.assertIsNotNone(confirmed)
        self.assertEqual(confirmed.payload["status"], "CONFIRMED")
        self.assertEqual(confirmed.payload["receipt_id"], submitted.payload["receipt_id"])
        self.assertEqual(confirmed.payload["confirmation_ref"], "0x99")
        self.assertEqual(confirmed.payload["confirmation_data"]["block_hash"], "0xblock")
        self.assertTrue(
            verify_execution_receipt(
                confirmed.as_dict(),
                load_public_key(self.public),
                auth,
            )[0]
        )
        stored = self.storage.execution_receipt_by_authorization(auth["payload"]["authorization_id"])
        self.assertEqual(stored["payload"]["status"], "CONFIRMED")

    def test_chain_failure_updates_receipt_to_failed(self):
        auth = self._auth()
        submitted = self.router.execute_with_receipt(auth, lambda tx: "0xabc")
        failed = self.router.confirm_execution_receipt(
            submitted.as_dict(),
            {
                "state": "FAILED",
                "transaction_ref": "0xabc",
                "block_ref": "0x99",
                "error": "transaction reverted",
            },
        )
        self.assertEqual(failed.payload["status"], "FAILED")
        self.assertEqual(failed.payload["transaction_ref"], "0xabc")
        self.assertIn("transaction reverted", failed.payload["error"])
        self.assertTrue(
            verify_execution_receipt(
                failed.as_dict(),
                load_public_key(self.public),
                auth,
            )[0]
        )

    def test_terminal_receipt_is_idempotent(self):
        auth = self._auth()
        submitted = self.router.execute_with_receipt(auth, lambda tx: "0xabc")
        confirmed = self.router.confirm_execution_receipt(
            submitted.as_dict(),
            {"state": "CONFIRMED", "transaction_ref": "0xabc", "block_ref": "0x99"},
        )
        again = self.router.confirm_execution_receipt(
            confirmed.as_dict(),
            {"state": "CONFIRMED", "transaction_ref": "0xabc", "block_ref": "0x99"},
        )
        self.assertEqual(again.as_dict(), confirmed.as_dict())


if __name__ == "__main__":
    unittest.main()
