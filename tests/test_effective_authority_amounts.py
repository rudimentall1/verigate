import unittest

from core.effective_authority import verify_effective_action


class EffectiveAuthorityAmountTest(unittest.TestCase):
    def test_decimal_string_amount_is_checked_against_numeric_limit(self):
        ok, reason = verify_effective_action(
            {"asset": "USDC", "amount": "1.25"},
            {"per_action_limits": {"USDC": 5.0}},
        )
        self.assertTrue(ok, reason)

    def test_exact_amount_above_limit_is_rejected_without_float_rounding(self):
        ok, reason = verify_effective_action(
            {"asset": "USDC", "amount": "5.000000000000000001"},
            {"per_action_limits": {"USDC": 5.0}},
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "execution amount exceeds effective authority")

    def test_invalid_or_non_finite_amount_fails_closed(self):
        for amount in ("not-a-number", "NaN", "Infinity", True, None):
            ok, _ = verify_effective_action(
                {"asset": "USDC", "amount": amount},
                {"per_action_limits": {"USDC": 5.0}},
            )
            self.assertFalse(ok)

    def test_exact_amount_at_limit_is_allowed(self):
        ok, reason = verify_effective_action(
            {"asset": "USDC", "amount": "5.000000000000000000"},
            {"per_action_limits": {"USDC": 5.0}},
        )
        self.assertTrue(ok, reason)


if __name__ == "__main__":
    unittest.main()
