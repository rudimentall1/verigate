"""Verigate API — FastAPI app.

Endpoints:
  POST /v1/check          evaluate a raw payment intent against policy
  POST /v1/check/x402      evaluate a payment parsed straight out of a real
                             x402 PAYMENT-REQUIRED header
  POST /v1/verify           independently verify a signed attestation
                             (does not require any prior state — a partner
                             or auditor can run this against nothing but
                             your public key)
  GET  /v1/agents/{id}/history
  GET  /health
  GET  /v1/public-key       fetch the issuer's public key (PEM), so
                             third parties can verify without an
                             out-of-band key exchange

Run: uvicorn api.main:app --reload
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.sign import sign_decision
from attest.verify import verify_attestation
from core.engine import GuardrailEngine
from core.models import PaymentIntent
from core.policy import Policy
from core.storage import Storage
from x402.parser import X402ParseError, offer_to_intent, parse_payment_required_header

from .schemas import (
    AttestationResponse,
    AuthorizationReceiptResponse,
    DecisionResponse,
    PaymentIntentRequest,
    VerifyRequest,
    VerifyResponse,
    X402HeaderRequest,
)

POLICY_PATH = os.environ.get("VERIGATE_POLICY", "policies/default.yaml")
DB_PATH = os.environ.get("VERIGATE_DB", "data/verigate.db")
PRIVATE_KEY_PATH = os.environ.get("VERIGATE_PRIVATE_KEY", "keys/issuer.key")
PUBLIC_KEY_PATH = os.environ.get("VERIGATE_PUBLIC_KEY", "keys/issuer.pub")

app = FastAPI(
    title="Verigate",
    description="A verifiable policy gate for autonomous agent payments (x402 and beyond).",
    version="0.1.0",
)

_policy: Policy | None = None
_storage: Storage | None = None
_engine: GuardrailEngine | None = None


@app.on_event("startup")
def _startup() -> None:
    global _policy, _storage, _engine
    if not Path(PRIVATE_KEY_PATH).exists():
        generate_keypair(PRIVATE_KEY_PATH, PUBLIC_KEY_PATH)
    _policy = Policy.load(POLICY_PATH)
    _storage = Storage(DB_PATH)
    _engine = GuardrailEngine(_policy, _storage)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/v1/public-key", response_class=PlainTextResponse)
def public_key() -> str:
    """Anyone can fetch this and verify attestations independently,
    without ever calling this API again."""
    return Path(PUBLIC_KEY_PATH).read_text()


def _decide_and_maybe_sign(intent: PaymentIntent, sign: bool) -> dict:
    assert _engine is not None and _storage is not None

    # GuardrailEngine evaluates AND records the attempt exactly once.
    decision = _engine.evaluate(intent)

    if sign:
        priv = load_private_key(PRIVATE_KEY_PATH)
        attestation = sign_decision(decision, priv)

        # Attach the signature to the existing audit row.
        _storage.update_signature(
            intent.intent_id,
            attestation.signature_b64,
        )

        return attestation.as_dict()

    return decision.as_dict()


@app.post("/v1/check", response_model=AttestationResponse | DecisionResponse)
def check(req: PaymentIntentRequest) -> dict:
    intent = PaymentIntent(
        agent_id=req.agent_id,
        payee=req.payee,
        asset=req.asset,
        network=req.network,
        amount=req.amount,
        resource=req.resource,
    )
    return _decide_and_maybe_sign(intent, req.sign)


@app.post("/v1/check/x402", response_model=AttestationResponse | DecisionResponse)
def check_x402(req: X402HeaderRequest) -> dict:
    try:
        offers = parse_payment_required_header(req.payment_required_header)
        intent = offer_to_intent(offers[0], agent_id=req.agent_id)
    except X402ParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _decide_and_maybe_sign(intent, req.sign)


@app.post("/v1/authorize", response_model=AuthorizationReceiptResponse)
def authorize(req: PaymentIntentRequest) -> dict:
    """Authorize a payment and return a portable signed authorization receipt.

    Unlike /v1/check, this endpoint makes the signed receipt the explicit
    authorization contract. Enforcement adapters can verify the receipt
    independently using the issuer public key.
    """
    assert _engine is not None
    intent = PaymentIntent(
        agent_id=req.agent_id,
        payee=req.payee,
        asset=req.asset,
        network=req.network,
        amount=req.amount,
        resource=req.resource,
    )
    private_key = load_private_key(PRIVATE_KEY_PATH)
    return _engine.authorize(intent, private_key).as_dict()


@app.post("/v1/authorize/x402", response_model=AuthorizationReceiptResponse)
def authorize_x402(req: X402HeaderRequest) -> dict:
    """Authorize the first x402 payment offer and return a signed receipt."""
    assert _engine is not None
    try:
        offers = parse_payment_required_header(req.payment_required_header)
        intent = offer_to_intent(offers[0], agent_id=req.agent_id)
    except X402ParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    private_key = load_private_key(PRIVATE_KEY_PATH)
    return _engine.authorize(intent, private_key).as_dict()


@app.post("/v1/verify", response_model=VerifyResponse)
def verify(req: VerifyRequest) -> dict:
    pub = load_public_key(PUBLIC_KEY_PATH)
    ok, reason = verify_attestation(req.model_dump(), pub)
    return {"valid": ok, "reason": reason}


@app.get("/v1/agents/{agent_id}/history")
def history(agent_id: str, limit: int = 20) -> list[dict]:
    assert _storage is not None
    return _storage.history(agent_id, limit=limit)
