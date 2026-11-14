from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authorization import AuthorizationService
from core.engine import GuardrailEngine
from core.models import ActionIntent, Decision
from core.policy import Policy
from core.storage import Storage
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter
from enforcement.solana_transaction import (
    SolanaTransactionError,
    parse_authorized_native_transfer,
)
from solana_fixtures import make_signed_transfer


class SolanaTransactionBindingTests(unittest.TestCase):
    def setUp(self):
        raw, sender, recipient = make_signed_transfer(1_000_000)
        self.action = {
            "network": "solana",
            "action_type": "native.transfer",
            "target": recipient,
            "amount": 0.001,
            "amount_exact": "0.001",
            "asset": "SOL",
            "metadata": {
                "solana_transaction": raw,
                "solana_sender": sender,
                "destination": recipient,
            },
        }

    def test_valid_signed_transfer_is_bound_to_intent(self):
        parsed = parse_authorized_native_transfer(self.action)
        self.assertEqual(parsed.sender, self.action["metadata"]["solana_sender"])
        self.assertEqual(parsed.recipient, self.action["target"])
        self.assertEqual(parsed.lamports, 1_000_000)
        self.assertTrue(parsed.signature)

    def test_recipient_mismatch_is_rejected(self):
        action = dict(self.action)
        action["target"] = "11111111111111111111111111111111"
        with self.assertRaisesRegex(SolanaTransactionError, "recipient"):
            parse_authorized_native_transfer(action)

    def test_amount_mismatch_is_rejected(self):
        action = dict(self.action)
        action["amount_exact"] = "0.002"
        with self.assertRaisesRegex(SolanaTransactionError, "amount"):
            parse_authorized_native_transfer(action)

    def test_sender_mismatch_is_rejected(self):
        action = dict(self.action)
        action["metadata"] = dict(self.action["metadata"])
        action["metadata"]["solana_sender"] = "11111111111111111111111111111111"
        with self.assertRaisesRegex(SolanaTransactionError, "sender"):
            parse_authorized_native_transfer(action)

    def test_modified_signature_is_rejected(self):
        action = dict(self.action)
        action["metadata"] = dict(self.action["metadata"])
        wire = bytearray(base64.b64decode(action["metadata"]["solana_transaction"]))
        wire[1] ^= 0x01
        action["metadata"]["solana_transaction"] = base64.b64encode(wire).decode("ascii")
        with self.assertRaisesRegex(SolanaTransactionError, "signature"):
            parse_authorized_native_transfer(action)


    def test_policy_block_mints_no_execution_authorization_and_never_broadcasts(self):
        raw, sender, recipient = make_signed_transfer(20_000_000)
        action = ActionIntent(
            agent_id="solana-policy-agent",
            action_type="native.transfer",
            target=recipient,
            amount=0.02,
            asset="SOL",
            network="solana",
            metadata={
                "solana_transaction": raw,
                "solana_sender": sender,
                "destination": recipient,
            },
        )
        policy = Policy(
            allowed_action_types=["native.transfer"],
            allowed_networks=["solana"],
            allowed_assets=["SOL"],
            per_tx_cap={"SOL": 0.01},
            raw={
                "allowed_action_types": ["native.transfer"],
                "allowed_networks": ["solana"],
                "allowed_assets": ["SOL"],
                "per_tx_cap": {"SOL": 0.01},
            },
        )
        with tempfile.TemporaryDirectory() as td:
            private_path = Path(td) / "issuer.key"
            public_path = Path(td) / "issuer.pub"
            generate_keypair(private_path, public_path)
            private_key = load_private_key(private_path)
            storage = Storage(Path(td) / "audit.db")
            try:
                engine = GuardrailEngine(policy, storage)
                decision = engine.evaluate_action(action)
                self.assertEqual(decision.decision, Decision.BLOCK)
                self.assertIn("per_tx_cap_exceeded", {m.rule_id for m in decision.matched_rules})

                artifacts = AuthorizationService().issue(
                    action,
                    decision,
                    policy.digest,
                    private_key,
                    nonce=action.intent_id,
                    policy=policy,
                )
                self.assertIsNone(artifacts["execution_authorization"])

                broadcasts = []
                router = ExecutionRouter(
                    NetworkRegistry(), storage, load_public_key(public_path), private_key
                )
                execution_authorization = artifacts["execution_authorization"]
                if execution_authorization is not None:
                    router.execute(execution_authorization, lambda tx: broadcasts.append(tx))
                self.assertEqual(broadcasts, [])
            finally:
                storage.close()

    def test_non_native_or_non_sol_action_fails_closed(self):
        action = dict(self.action)
        action["asset"] = "USDC"
        with self.assertRaisesRegex(SolanaTransactionError, "native SOL"):
            parse_authorized_native_transfer(action)


if __name__ == "__main__":
    unittest.main()
