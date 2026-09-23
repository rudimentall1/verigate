"""Verigate API  FastAPI app.

Endpoints:
  POST /v1/check
  POST /v1/check/x402
  POST /v1/authorize
  POST /v1/authorize/x402
  POST /v1/execution/consume
  GET  /v1/execution/networks
  POST /v1/verify
  GET  /v1/agents/{id}/history
  GET  /health
  GET  /v1/public-key
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.sign import sign_decision
from attest.verify import verify_attestation
from core.engine import GuardrailEngine
from core.models import PaymentIntent
from core.policy import Policy
from core.storage import Storage
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter
from x402.parser import X402ParseError, offer_to_intent, parse_payment_required_header

from .schemas import (
    AttestationResponse,
    AuthorizationResponse,
    DecisionResponse,
    ExecutionConsumeRequest,
    ExecutionConsumeResponse,
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

UI_DIR = Path(__file__).resolve().parent.parent / "ui"
app.mount("/demo", StaticFiles(directory=UI_DIR, html=True), name="demo-ui")

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


_DEMO_ROOT = Path(__file__).resolve().parent.parent


def _run_demo_script(script: str, timeout: int = 45) -> str:
    result = subprocess.run(
        [sys.executable, script],
        cwd=_DEMO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return result.stdout + ("\n" + result.stderr if result.stderr else "")


@app.get("/v1/demo/tamper")
def demo_tamper() -> dict:
    output = _run_demo_script("demo_tamper_enforcement.py", timeout=20)
    blocked = "VERIGATE: BLOCK" in output and "Broadcasts: 0" in output
    broadcasts = 0 if "Broadcasts: 0" in output else None
    return {"blocked": blocked, "broadcasts": broadcasts, "output": output[-5000:]}


@app.get("/v1/demo/live")
def demo_live() -> dict:
    try:
        output = _run_demo_script("demo_live_solana_devnet.py", timeout=50)
    except subprocess.TimeoutExpired as exc:
        return {"confirmed": False, "error": "Devnet execution timed out", "output": str(exc)}
    match = re.search(r"https://explorer\.solana\.com/tx/([^\s]+)\?cluster=devnet", output)
    confirmed = "RESULT: REAL DEVNET BROADCAST -> SUBMITTED -> CONFIRMED" in output
    return {
        "confirmed": confirmed,
        "signature": match.group(1) if match else None,
        "explorer": match.group(0) if match else None,
        "output": output[-7000:],
    }


@app.get("/v1/public-key", response_class=PlainTextResponse)
def public_key() -> str:
    return Path(PUBLIC_KEY_PATH).read_text()


def _decide_and_maybe_sign(intent: PaymentIntent, sign: bool) -> dict:
    assert _engine is not None and _storage is not None
    decision = _engine.evaluate(intent)
    if sign:
        priv = load_private_key(PRIVATE_KEY_PATH)
        attestation = sign_decision(decision, priv)
        _storage.update_signature(intent.intent_id, attestation.signature_b64)
        return attestation.as_dict()
    return decision.as_dict()


@app.post("/v1/check", response_model=AttestationResponse | DecisionResponse)
def check(req: PaymentIntentRequest) -> dict:
    intent = PaymentIntent(
        agent_id=req.agent_id, payee=req.payee, asset=req.asset, network=req.network,
        amount=req.amount, resource=req.resource,
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


@app.post("/v1/authorize", response_model=AuthorizationResponse)
def authorize(req: PaymentIntentRequest) -> dict:
    assert _engine is not None
    intent = PaymentIntent(
        agent_id=req.agent_id, payee=req.payee, asset=req.asset, network=req.network,
        amount=req.amount, resource=req.resource,
    )
    return _engine.authorize(intent, load_private_key(PRIVATE_KEY_PATH))


@app.post("/v1/authorize/x402", response_model=AuthorizationResponse)
def authorize_x402(req: X402HeaderRequest) -> dict:
    assert _engine is not None
    try:
        offers = parse_payment_required_header(req.payment_required_header)
        intent = offer_to_intent(offers[0], agent_id=req.agent_id)
    except X402ParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _engine.authorize(intent, load_private_key(PRIVATE_KEY_PATH))


@app.post("/v1/execution/consume", response_model=ExecutionConsumeResponse)
def consume_execution(req: ExecutionConsumeRequest) -> dict:
    """Consume a signed execution capability through the universal router."""
    assert _storage is not None
    router = ExecutionRouter(
        NetworkRegistry(),
        _storage,
        load_public_key(PUBLIC_KEY_PATH),
    )
    ok, reason = router.consume(req.authorization.model_dump())
    return {"execute": ok, "reason": reason}


@app.get("/v1/execution/networks")
def execution_networks() -> list[dict]:
    return NetworkRegistry().as_dict()


@app.get("/v1/execution/receipts/{authorization_id}")
def execution_receipt(authorization_id: str) -> dict:
    assert _storage is not None
    receipt = _storage.execution_receipt_by_authorization(authorization_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="execution receipt not found")
    return receipt


@app.post("/v1/verify", response_model=VerifyResponse)
def verify(req: VerifyRequest) -> dict:
    pub = load_public_key(PUBLIC_KEY_PATH)
    ok, reason = verify_attestation(req.model_dump(), pub)
    return {"valid": ok, "reason": reason}


@app.get("/v1/agents/{agent_id}/history")
def history(agent_id: str, limit: int = 20) -> list[dict]:
    assert _storage is not None
    return _storage.history(agent_id, limit=limit)
