from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "prepare_registration.py"
SPEC = importlib.util.spec_from_file_location("reactive_prepare_registration", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class PrepareRegistrationTests(unittest.TestCase):
    def test_exact_ether_amount_maps_to_wei(self):
        self.assertEqual(module._to_wei("0.125"), 125_000_000_000_000_000)

    def test_rejects_amount_that_cannot_be_represented_in_wei(self):
        with self.assertRaises(module.PreparationError):
            module._to_wei("0.0000000000000000001")

    def test_rejects_float_amount(self):
        with self.assertRaises(module.PreparationError):
            module._to_wei(0.1)

    def test_registration_transaction_encodes_all_nine_arguments(self):
        values = {
            "authorization_id": "11" * 32,
            "verigate_action_hash": "22" * 32,
            "policy_sha256": "33" * 32,
            "decision_receipt_sha256": "44" * 32,
            "recipient": "0x" + "55" * 20,
            "amount_wei": 123_456_789,
            "expires_at": 1_800_000_000,
        }
        hub = "0x" + "66" * 20
        issuer = "0x" + "77" * 20
        receiver = "0x" + "88" * 20

        transaction = module.build_registration_transaction(values, hub, issuer, receiver)

        self.assertEqual(transaction["chainId"], hex(module.BASE_SEPOLIA_CHAIN_ID))
        self.assertEqual(transaction["from"], issuer)
        self.assertEqual(transaction["to"], hub)
        self.assertEqual(transaction["value"], "0x0")
        self.assertTrue(transaction["data"].startswith("0x"))
        encoded = transaction["data"][10:]
        self.assertEqual(len(encoded), 9 * 64)
        words = [encoded[index * 64:(index + 1) * 64] for index in range(9)]
        self.assertEqual(words[0], values["authorization_id"])
        self.assertEqual(words[1], values["verigate_action_hash"])
        self.assertEqual(words[2], values["policy_sha256"])
        self.assertEqual(words[3], values["decision_receipt_sha256"])
        self.assertEqual(int(words[4], 16), module.UNICHAIN_SEPOLIA_CHAIN_ID)
        self.assertEqual(words[5], receiver[2:].rjust(64, "0"))
        self.assertEqual(words[6], values["recipient"][2:].rjust(64, "0"))
        self.assertEqual(int(words[7], 16), values["amount_wei"])
        self.assertEqual(int(words[8], 16), values["expires_at"])


if __name__ == "__main__":
    unittest.main()
