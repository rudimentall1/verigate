#!/usr/bin/env python3
"""CMC RWA -> Verigate authorization demo.

Live mode performs real CMC RWA API calls. Fixture mode is deterministic for
local tests and does not require an API key. No transaction is broadcast.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from attest.keys import generate_keypair, load_private_key
from adapters.cmc.client import CmcRwaClient
from adapters.cmc.models import CmcRwaQuote
from adapters.cmc.rwa import RwaPurchaseEvaluator


def fixture_quote(symbol: str) -> CmcRwaQuote:
    return CmcRwaQuote(
        rwa_id=1,
        name="Gold",
        symbol=symbol,
        slug="gold",
        asset_type="commodity",
        rwa_rank=1,
        has_tokens=True,
        average_tokenized_price=4000.0,
        tokenized_market_cap=1_000_000.0,
        tokenized_volume_24h=100_000.0,
        tokens=(
            {"symbol": "PAXG", "crypto_id": 4705, "price": 4000.0, "issuer_id": "issuer-paxos", "issuer_name": "Paxos"},
            {"symbol": "XAUM", "crypto_id": 34212, "price": 4001.0, "issuer_id": "issuer-matrix", "issuer_name": "Matrixdock"},
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="GOLD")
    parser.add_argument("--amount-usd", type=float, default=500.0)
    parser.add_argument("--fixture", action="store_true")
    args = parser.parse_args()

    policy_path = Path("hackathons/cmc-2026/policy.yaml")
    evaluator = RwaPurchaseEvaluator(
        RwaPurchaseEvaluator.load_policy(policy_path)
    )

    if args.fixture:
        quote = fixture_quote(args.symbol)
        print("CMC mode: FIXTURE")
    else:
        api_key = os.environ.get("CMC_API_KEY")
        if not api_key:
            raise SystemExit("CMC_API_KEY is required for live mode; use --fixture for offline demo")
        client = CmcRwaClient(api_key=api_key)
        mapping = client.resolve(symbol=args.symbol)
        assets = (mapping.get("data") or {}).get("rwa_assets") or []
        if not assets:
            raise SystemExit(f"CMC returned no RWA asset for symbol {args.symbol}")
        rwa_id = int(assets[0]["rwa_id"])
        print("CMC endpoint: /v5/real-world-assets/map")
        print("CMC map response:")
        print(json.dumps(assets[0], indent=2))
        quote = client.quote(rwa_id=rwa_id)
        print("CMC endpoint: /v5/real-world-assets/quotes/latest")
        print("CMC normalized quote:")
        print(json.dumps(quote.as_evidence(), indent=2))

    with tempfile.TemporaryDirectory(prefix="verigate-cmc-") as td:
        private = Path(td) / "issuer.key"
        public = Path(td) / "issuer.pub"
        generate_keypair(private, public)
        artifacts = evaluator.authorize_purchase(
            quote,
            args.amount_usd,
            load_private_key(private),
            agent_id="cmc-rwa-agent",
            settlement_network="base",
            evm_transaction={
                "chain_id": 8453,
                "to": "0xAUTHORIZED_TOKEN",
                "value_wei": 0,
                "data": "0x",
            },
        )

        print("Verigate decision:", artifacts["decision"]["decision"])
        print("Matched rules:")
        for rule in artifacts["decision"]["matched_rules"]:
            print(f"- {rule['rule']}: {rule['severity']} — {rule['message']}")
        print("Execution authorization issued:",
              artifacts["execution_authorization"] is not None)
        print("Action fingerprint:",
              artifacts["execution_authorization"]["payload"]["action_sha256"]
              if artifacts["execution_authorization"] else "n/a")

        block_amount = evaluator.policy.max_purchase_usd + 1
        blocked = evaluator.authorize_purchase(
            quote,
            block_amount,
            load_private_key(private),
            agent_id="cmc-rwa-agent",
            settlement_network="base",
            evm_transaction={
                "chain_id": 8453,
                "to": "0xAUTHORIZED_TOKEN",
                "value_wei": 0,
                "data": "0x",
            },
        )
        print("Verigate block test:", blocked["decision"]["decision"])
        for rule in blocked["decision"]["matched_rules"]:
            print(f"- BLOCKED: {rule['rule']} — {rule['message']}")
        print("Block test execution authorization:",
              blocked["execution_authorization"] is not None)
        print("No transaction was broadcast.")


if __name__ == "__main__":
    main()
