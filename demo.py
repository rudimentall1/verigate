#!/usr/bin/env python3
"""End-to-end demo: a merchant's x402 PAYMENT-REQUIRED header comes in, an
agent's payment intent is parsed out of it, evaluated against policy,
signed, and independently verified by a "third party" that never talks to
this process again. No live network calls — the x402 header is realistic,
static demo data (same shape real merchants emit), everything else runs
for real: real policy engine, real SQLite, real Ed25519 signatures.

Run: python3 demo.py
"""
from __future__ import annotations

import base64
import json
import tempfile
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.sign import sign_decision
from attest.verify import verify_attestation
from core.engine import GuardrailEngine
from core.policy import Policy
from core.storage import Storage
from x402.parser import offer_to_intent, parse_payment_required_header

SEP = "=" * 72


def make_header(pay_to: str, atomic_amount: str, network: str = "base") -> str:
    """Builds a realistic x402 v2 PAYMENT-REQUIRED header value the way a
    merchant server would emit it (base64-encoded JSON)."""
    data = {
        "x402Version": 2,
        "resource": "https://api.marketdata.example/v1/premium-feed",
        "accepts": [
            {
                "scheme": "exact",
                "network": network,
                "payTo": pay_to,
                "maxAmountRequired": atomic_amount,
                "extra": {"name": "USDC", "version": "2"},
                "resource": "https://api.marketdata.example/v1/premium-feed",
            }
        ],
    }
    return base64.b64encode(json.dumps(data).encode("utf-8")).decode("ascii")


def run_scenario(engine: GuardrailEngine, storage: Storage, priv, agent_id: str, header_b64: str, label: str) -> None:
    print(f"\n{SEP}\nSCENARIO: {label}\n{SEP}")
    offers = parse_payment_required_header(header_b64)
    offer = offers[0]
    print(f"x402 offer parsed: pay {offer.atomic_amount} atomic units of "
          f"{offer.asset} on {offer.network} to {offer.payee}")

    intent = offer_to_intent(offer, agent_id=agent_id)
    print(f"Normalized intent: {intent.amount} {intent.asset} -> {intent.payee}")

    decision = engine.evaluate(intent)
    print(f"Decision: {decision.decision.value}")
    for m in decision.matched_rules:
        print(f"  - [{m.severity.value}] {m.rule_id}: {m.message}")

    attestation = sign_decision(decision, priv)
    storage.record(intent, decision, attestation.signature_b64)

    print("Signed attestation issued (Ed25519, verifiable without server access).")


def main() -> None:
    tmpdir = Path(tempfile.mkdtemp(prefix="verigate-demo-"))
    priv_path = tmpdir / "issuer.key"
    pub_path = tmpdir / "issuer.pub"
    generate_keypair(priv_path, pub_path)
    priv = load_private_key(priv_path)
    pub = load_public_key(pub_path)

    policy = Policy.load("policies/default.yaml")
    storage = Storage(tmpdir / "audit.db")
    engine = GuardrailEngine(policy, storage)

    agent = "market-research-agent-07"

    # Scenario 1: small, routine payment to a data feed -> clean ALLOW.
    run_scenario(
        engine, storage, priv, agent,
        make_header("0xDataFeedMerchant", "3000000"),  # 3.0 USDC
        "Routine data-feed purchase, well within policy",
    )

    # Scenario 2: first-ever payment to a brand-new payee, over the
    # new-payee cap -> WARN, needs a human's confirmation.
    run_scenario(
        engine, storage, priv, agent,
        make_header("0xNeverSeenBefore", "100000000"),  # 100.0 USDC
        "First payment to an unfamiliar payee, over the new-payee cap",
    )

    # Scenario 3: a runaway/compromised agent tries to push a payment far
    # over the per-transaction cap -> hard BLOCK.
    header_3 = make_header("0xDataFeedMerchant", "50000000000")  # 50,000 USDC
    print(f"\n{SEP}\nSCENARIO: Runaway agent attempts a payment far over the per-tx cap\n{SEP}")
    offers = parse_payment_required_header(header_3)
    intent_3 = offer_to_intent(offers[0], agent_id=agent)
    decision_3 = engine.evaluate(intent_3)
    print(f"Decision: {decision_3.decision.value}")
    for m in decision_3.matched_rules:
        print(f"  - [{m.severity.value}] {m.rule_id}: {m.message}")
    attestation_3 = sign_decision(decision_3, priv)
    storage.record(intent_3, decision_3, attestation_3.signature_b64)

    # Now prove the BLOCK is independently verifiable — and that tampering
    # with it after the fact is detectable — without touching this process
    # or its database ever again.
    print(f"\n{SEP}\nTHIRD-PARTY VERIFICATION (simulating an auditor/partner)\n{SEP}")
    att_dict = attestation_3.as_dict()
    ok, reason = verify_attestation(att_dict, pub)
    print(f"Verifying the genuine BLOCK attestation: valid={ok} — {reason}")

    tampered = json.loads(json.dumps(att_dict))
    tampered["payload"]["decision"] = "ALLOW"
    ok2, reason2 = verify_attestation(tampered, pub)
    print(f"Verifying a tampered copy (BLOCK silently flipped to ALLOW): "
          f"valid={ok2} — {reason2}")

    print(f"\n{SEP}\nAGENT HISTORY (from the audit log)\n{SEP}")
    for row in storage.history(agent):
        print(f"  {row['decision']:5s}  {row['amount']:>10.2f} {row['asset']} -> {row['payee']}")

    storage.close()
    print(f"\nDemo artifacts written to a temp dir at: {tmpdir}")


if __name__ == "__main__":
    main()
