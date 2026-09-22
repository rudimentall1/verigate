import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.receipt import verify_execution_authorization
from adapters.cmc.client import CmcApiError, CmcRwaClient
from adapters.cmc.models import CmcRwaQuote
from adapters.cmc.rwa import RwaPolicy, RwaPurchaseEvaluator


class CmcClientTest(unittest.TestCase):
    def _payload(self):
        return {
            "data": {
                "rwa_id": 1,
                "name": "Gold",
                "symbol": "GOLD",
                "slug": "gold",
                "asset_type": "commodity",
                "rwa_rank": 1,
                "has_tokens": True,
                "average_tokenized_price": 4000.0,
                "tokenized_market_cap": 1000000.0,
                "tokenized_volume_24h": 100000.0,
                "tokens": [{"symbol": "PAXG", "crypto_id": 4705, "price": 4000.0}],
                "tradfi_markets": [],
            },
            "status": {"error_code": 0, "timestamp": "2026-09-22T12:00:00Z"},
        }

    def test_quote_uses_dedicated_rwa_endpoint(self):
        calls = []
        def transport(url, headers, timeout):
            calls.append((url, headers))
            return self._payload()

        quote = CmcRwaClient(
            api_key="secret",
            transport=transport,
        ).quote(symbol="GOLD")
        self.assertEqual(quote.rwa_id, 1)
        self.assertEqual(quote.asset_type, "commodity")
        self.assertIn("/v5/real-world-assets/quotes/latest", calls[0][0])
        self.assertEqual(calls[0][1]["X-CMC_PRO_API_KEY"], "secret")

    def test_selector_requires_exactly_one_identifier(self):
        client = CmcRwaClient(transport=lambda *_: self._payload())
        with self.assertRaises(ValueError):
            client.quote()
        with self.assertRaises(ValueError):
            client.quote(symbol="GOLD", rwa_id=1)

    def test_api_error_is_surfaced(self):
        payload = {"data": {}, "status": {"error_code": 1001, "error_message": "bad key"}}
        client = CmcRwaClient(transport=lambda *_: payload)
        with self.assertRaises(CmcApiError):
            client.quote(symbol="GOLD")


class RwaPolicyTest(unittest.TestCase):
    def setUp(self):
        self.quote = CmcRwaQuote(
            rwa_id=1,
            name="Gold",
            symbol="GOLD",
            slug="gold",
            asset_type="commodity",
            rwa_rank=1,
            has_tokens=True,
            average_tokenized_price=4000.0,
            tokenized_market_cap=1_000_000.0,
            tokenized_volume_24h=100_000.0,
        )

    def test_small_purchase_is_allow(self):
        evaluator = RwaPurchaseEvaluator()
        action = evaluator.build_action(self.quote, 500, agent_id="agent-rwa")
        decision = evaluator.evaluate(action, self.quote, 500)
        self.assertEqual(decision.decision.value, "ALLOW")

    def test_large_share_of_volume_is_warn(self):
        evaluator = RwaPurchaseEvaluator()
        action = evaluator.build_action(self.quote, 2_000, agent_id="agent-rwa")
        decision = evaluator.evaluate(action, self.quote, 2_000)
        self.assertEqual(decision.decision.value, "WARN")
        self.assertEqual(decision.matched_rules[0].rule_id, "rwa_volume_fraction_high")
    def test_purchase_cap_is_block(self):
        evaluator = RwaPurchaseEvaluator(RwaPolicy(max_purchase_usd=100))
        action = evaluator.build_action(self.quote, 101, agent_id="agent-rwa")
        decision = evaluator.evaluate(action, self.quote, 101)
        self.assertEqual(decision.decision.value, "BLOCK")

    def test_unsupported_rwa_type_is_block(self):
        quote = CmcRwaQuote(
            rwa_id=2,
            name="Odd",
            symbol="ODD",
            slug="odd",
            asset_type="unknown",
            rwa_rank=None,
            has_tokens=True,
            average_tokenized_price=1.0,
            tokenized_market_cap=1_000_000.0,
            tokenized_volume_24h=100_000.0,
        )
        evaluator = RwaPurchaseEvaluator()
        action = evaluator.build_action(quote, 100, agent_id="agent-rwa")
        decision = evaluator.evaluate(action, quote, 100)
        self.assertEqual(decision.decision.value, "BLOCK")

    def test_allow_mints_execution_capability_with_cmc_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            private = Path(td) / "issuer.key"
            public = Path(td) / "issuer.pub"
            generate_keypair(private, public)
            evaluator = RwaPurchaseEvaluator()
            artifacts = evaluator.authorize_purchase(
                self.quote,
                500,
                load_private_key(private),
                agent_id="agent-rwa",
                settlement_network="base",
                evm_transaction={
                    "chain_id": 8453,
                    "to": "0xasset",
                    "value_wei": 0,
                    "data": "0x",
                },
            )
            self.assertEqual(artifacts["decision"]["decision"], "ALLOW")
            execution = artifacts["execution_authorization"]
            self.assertIsNotNone(execution)
            self.assertEqual(
                execution["payload"]["action"]["metadata"]["source"],
                "coinmarketcap.rwa.v5",
            )
            self.assertTrue(
                verify_execution_authorization(
                    execution,
                    load_public_key(public),
                )[0]
            )
    def test_warn_does_not_mint_execution_capability(self):
        evaluator = RwaPurchaseEvaluator()
        artifacts = evaluator.authorize_purchase(
            self.quote,
            2_000,
            load_private_key(self._keys()[0]),
        )
        self.assertEqual(artifacts["decision"]["decision"], "WARN")
        self.assertIsNone(artifacts["execution_authorization"])

    def _keys(self):
        td = tempfile.TemporaryDirectory()
        private = Path(td.name) / "issuer.key"
        public = Path(td.name) / "issuer.pub"
        generate_keypair(private, public)
        self.addCleanup(td.cleanup)
        return private, public


if __name__ == "__main__":
    unittest.main()
