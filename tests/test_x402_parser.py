import base64
import json
import unittest

from x402.parser import X402ParseError, offer_to_intent, parse_payment_required_header


def _encode(data: dict) -> str:
    return base64.b64encode(json.dumps(data).encode("utf-8")).decode("ascii")


class X402ParserTest(unittest.TestCase):
    def test_parses_valid_header(self):
        header = _encode(
            {
                "resource": "https://api.example.com/premium-data",
                "accepts": [
                    {
                        "payTo": "0xMerchant123",
                        "network": "base",
                        "maxAmountRequired": "5000000",  # 5 USDC at 6 decimals
                        "extra": {"name": "USDC"},
                    }
                ],
            }
        )
        offers = parse_payment_required_header(header)
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].payee, "0xMerchant123")
        self.assertEqual(offers[0].asset, "USDC")

        intent = offer_to_intent(offers[0], agent_id="agent-1")
        self.assertAlmostEqual(intent.amount, 5.0)
        self.assertEqual(intent.network, "base")

    def test_multiple_offers(self):
        header = _encode(
            {
                "accepts": [
                    {"payTo": "0xA", "network": "base", "maxAmountRequired": "1000000", "extra": {"name": "USDC"}},
                    {"payTo": "0xA", "network": "solana", "maxAmountRequired": "2000000", "extra": {"name": "USDC"}},
                ]
            }
        )
        offers = parse_payment_required_header(header)
        self.assertEqual(len(offers), 2)

    def test_rejects_invalid_base64(self):
        with self.assertRaises(X402ParseError):
            parse_payment_required_header("not-valid-base64!!!")

    def test_rejects_missing_accepts(self):
        header = _encode({"resource": "x"})
        with self.assertRaises(X402ParseError):
            parse_payment_required_header(header)

    def test_refuses_to_guess_unknown_asset_decimals(self):
        header = _encode(
            {
                "accepts": [
                    {
                        "payTo": "0xA",
                        "network": "some-new-chain",
                        "maxAmountRequired": "100",
                        "extra": {"name": "MYSTERYCOIN"},
                    }
                ]
            }
        )
        offers = parse_payment_required_header(header)
        with self.assertRaises(X402ParseError):
            offer_to_intent(offers[0], agent_id="agent-1")


if __name__ == "__main__":
    unittest.main()
