#!/usr/bin/env python3
"""Compact live demo for recording: CMC RWA -> ALLOW -> BLOCK."""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from attest.keys import generate_keypair, load_private_key
from adapters.cmc.client import CmcRwaClient
from adapters.cmc.rwa import RwaPurchaseEvaluator


def main() -> None:
    api_key = os.environ.get("CMC_API_KEY")
    if not api_key:
        raise SystemExit("CMC_API_KEY is required")

    evaluator = RwaPurchaseEvaluator.load_policy(
        Path("hackathons/cmc-2026/policy.yaml")
    )
    client = CmcRwaClient(api_key=api_key)

    print()
    print("=" * 62)
    print("VERIGATE  |  LIVE RWA EXECUTION GUARD")
    print("=" * 62)
    mapping = client.resolve(symbol="GOLD")
    assets = (mapping.get("data") or {}).get("rwa_assets") or []
    if not assets:
        raise SystemExit("CMC returned no GOLD RWA asset")

    rwa = assets[0]
    quote = client.quote(rwa_id=int(rwa["rwa_id"]))

    print("CMC: LIVE  /v5/real-world-assets/map")
    print("CMC: LIVE  /v5/real-world-assets/quotes/latest")
    print(f"Asset: {quote.name} ({quote.symbol})")
    print("Price: $" + f"{quote.average_tokenized_price:,.2f}")
    print("Tokenized 24h volume: $" + f"{quote.tokenized_volume_24h:,.0f}")
    print()
    time.sleep(2)

    with tempfile.TemporaryDirectory(prefix="verigate-video-") as td:
        private = Path(td) / "issuer.key"
        public = Path(td) / "issuer.pub"
        generate_keypair(private, public)

        print("ACTION 1  |  Buy Gold for $500")
        allowed = evaluator.authorize_purchase(
            quote,
            500,
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
        print(f"VERIGATE: {allowed['decision']['decision']}")
        print(
            "Execution permission:",
            "GRANTED" if allowed["execution_authorization"] else "DENIED",
        )
        print()
        time.sleep(3)

        print("ACTION 2  |  Buy Gold for $5,001")
        blocked = evaluator.authorize_purchase(
            quote,
            evaluator.policy.max_purchase_usd + 1,
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
        print(f"VERIGATE: {blocked['decision']['decision']}")
        print(
            "Execution permission:",
            "GRANTED" if blocked["execution_authorization"] else "DENIED",
        )
        print("Reason: purchase exceeds the $5,000 limit")
        print()
        print("No transaction was broadcast.")
        print("=" * 62)


if __name__ == "__main__":
    main()
