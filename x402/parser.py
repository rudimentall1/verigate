"""Parses a real x402 v2 PAYMENT-REQUIRED header (base64-encoded JSON) into
a normalized core.models.PaymentIntent that the policy engine can evaluate.

Deliberately refuses to guess at anything it doesn't recognize (asset
decimals, unfamiliar network names) rather than silently misjudging an
amount — the same boundary this design holds for EIP-3009 domain
construction: an unrecognized case returns an error, not a guess.
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from core.models import PaymentIntent

# atomic-unit decimals for known assets — extend as you verify more.
_KNOWN_DECIMALS = {
    ("USDC", "base"): 6,
    ("USDC", "ethereum"): 6,
    ("USDC", "solana"): 6,
}


class X402ParseError(ValueError):
    pass


@dataclass(frozen=True)
class X402Offer:
    payee: str
    asset: str
    network: str
    atomic_amount: int
    resource: str


def parse_payment_required_header(header_b64: str) -> list[X402Offer]:
    """Decodes the base64 PAYMENT-REQUIRED header value into a list of
    payment offers (x402 allows multiple `accepts[]` options)."""
    try:
        raw = base64.b64decode(header_b64)
        data = json.loads(raw)
    except Exception as exc:
        raise X402ParseError(f"could not decode PAYMENT-REQUIRED header: {exc}") from exc

    accepts = data.get("accepts")
    if not isinstance(accepts, list) or not accepts:
        raise X402ParseError("PAYMENT-REQUIRED header has no 'accepts' offers")

    offers: list[X402Offer] = []
    for offer in accepts:
        try:
            offers.append(
                X402Offer(
                    payee=offer["payTo"],
                    asset=offer["extra"]["name"].upper(),
                    network=offer["network"],
                    atomic_amount=int(offer["maxAmountRequired"]),
                    resource=offer.get("resource", data.get("resource", "")),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise X402ParseError(f"malformed offer in 'accepts[]': {exc}") from exc

    return offers


def offer_to_intent(offer: X402Offer, agent_id: str) -> PaymentIntent:
    key = (offer.asset, offer.network)
    decimals = _KNOWN_DECIMALS.get(key)
    if decimals is None:
        raise X402ParseError(
            f"unrecognized asset/network pair {key} — refusing to guess decimals "
            f"rather than silently misjudge the amount. Add it to _KNOWN_DECIMALS "
            f"once verified against the issuer's own docs."
        )
    amount = offer.atomic_amount / (10**decimals)
    return PaymentIntent(
        agent_id=agent_id,
        payee=offer.payee,
        asset=offer.asset,
        network=offer.network,
        amount=amount,
        resource=offer.resource,
    )
