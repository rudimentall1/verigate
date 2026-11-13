from __future__ import annotations

import base64
import unittest

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

    def test_non_native_or_non_sol_action_fails_closed(self):
        action = dict(self.action)
        action["asset"] = "USDC"
        with self.assertRaisesRegex(SolanaTransactionError, "native SOL"):
            parse_authorized_native_transfer(action)


if __name__ == "__main__":
    unittest.main()
