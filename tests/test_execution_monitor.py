import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authorization import AuthorizationService
from core.models import ActionIntent, Decision, GuardrailDecision
from core.storage import Storage
from enforcement.monitor import ExecutionMonitor
from enforcement.router import ExecutionRouter
from enforcement.networks import NetworkRegistry, UnsupportedNetworkError


class ExecutionMonitorTest(unittest.TestCase):
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

    def _receipt(self):
        intent = ActionIntent(
            agent_id="monitor-agent",
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
        auth = AuthorizationService().issue(
            intent,
            decision,
            "monitor-policy",
            load_private_key(self.private),
            nonce=intent.intent_id,
        )["execution_authorization"]
        return self.router.execute_with_receipt(auth, lambda tx: "0xabc")

    def test_pending_provider_state_is_returned(self):
        receipt = self._receipt()
        monitor = ExecutionMonitor({
            "base": type("Provider", (), {
                "confirm_transaction": lambda self, ref: {
                    "state": "PENDING",
                    "transaction_ref": ref,
                }
            })()
        })
        result = monitor.check(receipt.as_dict())
        self.assertEqual(result["state"], "PENDING")

    def test_confirmation_provider_is_selected_by_network(self):
        receipt = self._receipt()
        monitor = ExecutionMonitor({
            "base": type("Provider", (), {
                "confirm_transaction": lambda self, ref: {
                    "state": "CONFIRMED",
                    "transaction_ref": ref,
                    "block_ref": "0x99",
                }
            })()
        })
        result = monitor.check(receipt.as_dict())
        self.assertEqual(result["state"], "CONFIRMED")
        self.assertEqual(result["transaction_ref"], "0xabc")

    def test_missing_provider_fails_closed(self):
        receipt = self._receipt()
        with self.assertRaises(UnsupportedNetworkError):
            ExecutionMonitor({}).check(receipt.as_dict())

    def test_terminal_receipt_does_not_query_provider(self):
        receipt = self._receipt()
        confirmed = self.router.confirm_execution_receipt(
            receipt.as_dict(),
            {"state": "CONFIRMED", "transaction_ref": "0xabc", "block_ref": "0x99"},
        )
        monitor = ExecutionMonitor({})
        result = monitor.check(confirmed.as_dict())
        self.assertEqual(result["state"], "CONFIRMED")


if __name__ == "__main__":
    unittest.main()
