import unittest
from decimal import Decimal

from core.authority_protocol import authority_ceiling_allows


class AuthorityCeilingAmountNormalizationTest(unittest.TestCase):
    def test_accepts_decimal_strings_from_json_boundaries(self):
        self.assertTrue(
            authority_ceiling_allows("2000000000", "1.0", "1000000")
        )

    def test_accepts_amount_equal_to_exact_dynamic_ceiling(self):
        self.assertTrue(
            authority_ceiling_allows(Decimal("0.3"), Decimal("0.1"), "0.03")
        )

    def test_rejects_amount_above_exact_dynamic_ceiling(self):
        self.assertFalse(
            authority_ceiling_allows("0.3", "0.1", "0.030000000000000001")
        )

    def test_rejects_invalid_or_non_finite_values_closed(self):
        for value in ("not-a-number", "NaN", "Infinity", True, None):
            with self.subTest(value=value):
                self.assertFalse(authority_ceiling_allows(value, "1", "0"))

    def test_rejects_negative_values_and_multiplier_above_one(self):
        self.assertFalse(authority_ceiling_allows("-1", "1", "0"))
        self.assertFalse(authority_ceiling_allows("1", "-0.1", "0"))
        self.assertFalse(authority_ceiling_allows("1", "1.0001", "0"))
        self.assertFalse(authority_ceiling_allows("1", "1", "-0.1"))


if __name__ == "__main__":
    unittest.main()
