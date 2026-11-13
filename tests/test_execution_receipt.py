import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.receipt import sign_execution_receipt, verify_execution_receipt
from core.authorization import AuthorizationService
from core.models import ActionIntent, Capability, Decision, GuardrailDecision
from core.storage import Storage
from core.authority_state import DynamicAuthorityService
from core.policy import Policy
from enforcement.evm import EVMExecutionAdapter
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter
from enforcement.solana import SolanaExecutionAdapter
from solana_fixtures import make_signed_transfer


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
        if network == "solana":
            action_type = "native.transfer"
            target = metadata["destination"]
            asset = "SOL"
            amount = 0.001
        else:
            action_type = "token.transfer"
            target = "merchant"
            asset = "USDC"
            amount = None
        intent = ActionIntent(
            agent_id="receipt-agent",
            action_type=action_type,
            target=target,
            amount=amount,
            asset=asset,
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
            allowed_actions=(action_type,),
            allowed_targets=(target,),
            allowed_networks=(network,),
            allowed_assets=(asset,),
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
        raw, sender_address, recipient_address = make_signed_transfer()
        auth = self._authorization(
            "solana",
            {
                "solana_transaction": raw,
                "solana_sender": sender_address,
                "destination": recipient_address,
            },
        )
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


    def test_wallet_outcome_receipts_are_signed_and_status_specific(self):
        auth = self._authorization(
            "base",
            {"evm_transaction": {"chain_id": 8453, "to": "0xMerchant", "value_wei": 0, "data": "0x"}},
        )
        cases = (
            ("REJECTED", "wallet_request", 4001, "User rejected transaction signature"),
            ("ABORTED", "pre_wallet_request", None, "Wallet account changed before submission"),
            ("ABORTED", "router_response_unknown", None, "Router response was lost; wallet was not called"),
            ("UNKNOWN", "wallet_request", 4900, "Wallet connection was lost while awaiting submission"),
        )
        for status, phase, error_code, message in cases:
            with self.subTest(status=status, phase=phase):
                receipt = sign_execution_receipt(
                    auth,
                    status=status,
                    transaction_ref=None,
                    executor="anna-eip1193-wallet",
                    private_key=load_private_key(self.private),
                    error=message,
                    submission_data={
                        "source": "anna_eip1193_wallet",
                        "phase": phase,
                        "error_code": error_code,
                        "sender": "0x" + "11" * 20,
                    },
                ).as_dict()
                self.assertEqual(receipt["payload"]["transaction_ref"], None)
                self.assertTrue(
                    verify_execution_receipt(receipt, load_public_key(self.public), auth)[0]
                )

    def test_wallet_outcome_receipt_rejects_false_status_claims(self):
        auth = self._authorization(
            "base",
            {"evm_transaction": {"chain_id": 8453, "to": "0xMerchant", "value_wei": 0, "data": "0x"}},
        )
        invalid_cases = (
            ("REJECTED", "wallet_request", 4900),
            ("UNKNOWN", "wallet_request", 4001),
            ("ABORTED", "wallet_request", None),
            ("REJECTED", "pre_wallet_request", 4001),
        )
        for status, phase, error_code in invalid_cases:
            with self.subTest(status=status, phase=phase, error_code=error_code):
                with self.assertRaises(ValueError):
                    sign_execution_receipt(
                        auth,
                        status=status,
                        transaction_ref=None,
                        executor="anna-eip1193-wallet",
                        private_key=load_private_key(self.private),
                        error="wallet outcome",
                        submission_data={
                            "source": "anna_eip1193_wallet",
                            "phase": phase,
                            "error_code": error_code,
                        },
                    )

    def test_wallet_outcome_receipt_tampering_fails_verification(self):
        auth = self._authorization(
            "base",
            {"evm_transaction": {"chain_id": 8453, "to": "0xMerchant", "value_wei": 0, "data": "0x"}},
        )
        receipt = sign_execution_receipt(
            auth,
            status="REJECTED",
            transaction_ref=None,
            executor="anna-eip1193-wallet",
            private_key=load_private_key(self.private),
            error="User rejected transaction signature",
            submission_data={
                "source": "anna_eip1193_wallet",
                "phase": "wallet_request",
                "error_code": 4001,
            },
        ).as_dict()
        receipt["payload"]["submission_data"]["error_code"] = 4100
        ok, reason = verify_execution_receipt(receipt, load_public_key(self.public), auth)
        self.assertFalse(ok)
        self.assertNotEqual(reason, "valid execution receipt")


if __name__ == "__main__":
    unittest.main()
