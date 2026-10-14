"""Regression tests for exact decimal values in effective authority verification."""

from __future__ import annotations

import unittest

from core.effective_authority import verify_effective_action


class EffectiveAuthorityDecimalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.action = {
            "action_type": "portaldot.native_transfer",
            "target": "0x1111111111111111111111111111111111111111",
            "resource": "portaldot-native-payment-demo",
            "asset": "tPOTv3",
            "network": "portaldot-v3",
            "purpose": "portaldot-hacker-house-demo",
            "amount": "1000000",
            "amount_exact": "1000000",
        }
        self.authority = {"per_action_limits": {"tPOTv3": 2_000_000_000.0}}

    def test_decimal_string_amount_within_limit_is_allowed(self) -> None:
        valid, reason = verify_effective_action(self.action, self.authority)
        self.assertTrue(valid, reason)

    def test_decimal_string_amount_over_limit_is_rejected(self) -> None:
        self.action["amount"] = "3000000000"
        self.action["amount_exact"] = "3000000000"
        valid, reason = verify_effective_action(self.action, self.authority)
        self.assertFalse(valid)
        self.assertEqual(reason, "execution amount exceeds effective authority")

    def test_mismatched_amount_representations_are_rejected(self) -> None:
        self.action["amount"] = "3000000000"
        valid, reason = verify_effective_action(self.action, self.authority)
        self.assertFalse(valid)
        self.assertIn("amount", reason)

    def test_invalid_decimal_amount_fails_closed(self) -> None:
        self.action["amount"] = "NaN"
        self.action["amount_exact"] = "NaN"
        valid, reason = verify_effective_action(self.action, self.authority)
        self.assertFalse(valid)
        self.assertEqual(reason, "execution amount exceeds effective authority")


if __name__ == "__main__":
    unittest.main()
