"""Verigate API  FastAPI app.

Endpoints:
  POST /v1/check
  POST /v1/check/x402
  POST /v1/authorize
  POST /v1/authorize/capability
  POST /v1/authorize/identity
  POST /v1/actions/authorize
  POST /v1/authorize/x402
  POST /v1/execution/consume
  GET  /v1/execution/networks
  GET  /v1/authority/capabilities/{id}
  POST /v1/verify
  GET  /v1/agents/{id}/history
  GET  /health
  GET  /v1/public-key
  GET  /v1/governance/public-key
  GET  /v1/governance/policy
  POST /v1/authority/reset
  POST /v1/authority/reset/multi
  POST /v1/policies/governed/publish
  GET  /v1/policies/governed/{policy_sha256}
  POST /v1/policies/governed/freeze
  POST /v1/policies/governed/rollback
"""
from __future__ import annotations

import json
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
from attest.receipt import verify_execution_authorization
from core.adversarial import AdversarialVerificationPlane
from core.authority import AuthorityGraph
from core.authority_state import DynamicAuthorityService
from core.engine import GuardrailEngine
from core.evidence import EvidenceGraph
from core.governance import (
    AuthorityGovernanceService,
    GovernanceMember,
    GovernancePolicy,
    MultiPartyAuthorityGovernanceService,
)
from core.models import ActionIntent, PaymentIntent
from core.policy import Policy
from core.policy_version import (
    GovernedPolicyControlService,
    GovernedPolicyVersionRegistry,
)
from core.storage import Storage
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter
from x402.parser import X402ParseError, offer_to_intent, parse_payment_required_header

from .schemas import (
    AttestationResponse,
    AuthorizationResponse,
    AdversarialVerificationRequest,
    AdversarialVerificationResponse,
    AuthorityResetRequest,
    AuthorityResetResponse,
    MultiPartyAuthorityResetRequest,
    MultiPartyAuthorityResetResponse,
    ActionAuthorizationRequest,
    CapabilityAuthorizationRequest,
    IdentityAuthorizationRequest,
    DecisionResponse,
    ExecutionConsumeRequest,
    ExecutionConsumeResponse,
    PaymentIntentRequest,
    VerifyRequest,
    VerifyResponse,
    GovernedPolicyPublishRequest,
    GovernedPolicyPublishResponse,
    GovernedPolicyControlRequest,
    GovernedPolicyControlResponse,
    X402HeaderRequest,
)

POLICY_PATH = os.environ.get("VERIGATE_POLICY", "policies/default.yaml")
DB_PATH = os.environ.get("VERIGATE_DB", "data/verigate.db")
PRIVATE_KEY_PATH = os.environ.get("VERIGATE_PRIVATE_KEY", "keys/issuer.key")
PUBLIC_KEY_PATH = os.environ.get("VERIGATE_PUBLIC_KEY", "keys/issuer.pub")
GOVERNANCE_PRIVATE_KEY_PATH = os.environ.get(
    "VERIGATE_GOVERNANCE_PRIVATE_KEY",
    "keys/governance.key",
)
GOVERNANCE_PUBLIC_KEY_PATH = os.environ.get(
    "VERIGATE_GOVERNANCE_PUBLIC_KEY",
    "keys/governance.pub",
)
GOVERNANCE_POLICY_PATH = os.environ.get(
    "VERIGATE_GOVERNANCE_POLICY",
    "config/governance-policy.json",
)
REQUIRE_GOVERNED_POLICY = os.environ.get(
    "VERIGATE_REQUIRE_GOVERNED_POLICY",
    "",
).lower() in {"1", "true", "yes"}

app = FastAPI(
    title="Verigate",
    description="Agent Authority Control Plane for autonomous agents: identity, capability, governance, authorization, execution and evidence.",
    version="0.1.0",
)

UI_DIR = Path(__file__).resolve().parent.parent / "ui"
app.mount("/demo", StaticFiles(directory=UI_DIR, html=True), name="demo-ui")

_policy: Policy | None = None
_storage: Storage | None = None
_engine: GuardrailEngine | None = None
_governance_policy: GovernancePolicy | None = None


def _load_governance_policy() -> GovernancePolicy:
    policy_path = Path(GOVERNANCE_POLICY_PATH)
    if policy_path.exists():
        data = json.loads(policy_path.read_text(encoding="utf-8"))
        return GovernancePolicy.from_dict(data)
    public_key = load_public_key(GOVERNANCE_PUBLIC_KEY_PATH)
    policy = GovernancePolicy(
        policy_id="verigate-local-single-governor",
        version=1,
        threshold=1,
        members=(GovernanceMember.from_public_key(public_key, "governor"),),
    )
    policy.validate()
    return policy


@app.on_event("startup")
def _startup() -> None:
    global _policy, _storage, _engine, _governance_policy
    if not Path(PRIVATE_KEY_PATH).exists():
        generate_keypair(PRIVATE_KEY_PATH, PUBLIC_KEY_PATH)
    if not Path(GOVERNANCE_PRIVATE_KEY_PATH).exists():
        generate_keypair(
            GOVERNANCE_PRIVATE_KEY_PATH,
            GOVERNANCE_PUBLIC_KEY_PATH,
        )
    _policy = Policy.load(POLICY_PATH)
    _storage = Storage(DB_PATH)
    _engine = GuardrailEngine(
        _policy,
        _storage,
        policy_source_ref=POLICY_PATH,
        require_governed_policy=REQUIRE_GOVERNED_POLICY,
    )
    _governance_policy = _load_governance_policy()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


_DEMO_ROOT = Path(__file__).resolve().parent.parent
ENABLE_DEMO_ENDPOINTS = os.environ.get("VERIGATE_ENABLE_DEMO_ENDPOINTS", "").lower() in {"1", "true", "yes"}
ENABLE_DEMO_TAMPER = os.environ.get("VERIGATE_ENABLE_DEMO_TAMPER", "").lower() in {"1", "true", "yes"}


def _require_demo_endpoints(*, live: bool = False) -> None:
    enabled = ENABLE_DEMO_ENDPOINTS if live else (ENABLE_DEMO_ENDPOINTS or ENABLE_DEMO_TAMPER)
    if not enabled:
        raise HTTPException(status_code=404, detail="demo endpoint is disabled")


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
    _require_demo_endpoints()
    output = _run_demo_script("demo_tamper_enforcement.py", timeout=20)
    blocked = "VERIGATE: BLOCK" in output and "Broadcasts: 0" in output
    broadcasts = 0 if "Broadcasts: 0" in output else None
    return {"blocked": blocked, "broadcasts": broadcasts, "output": output[-5000:]}


@app.get("/v1/demo/live")
def demo_live() -> dict:
    _require_demo_endpoints(live=True)
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


@app.get("/v1/governance/public-key", response_class=PlainTextResponse)
def governance_public_key() -> str:
    return Path(GOVERNANCE_PUBLIC_KEY_PATH).read_text()


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


@app.post("/v1/authorize/capability", response_model=AuthorizationResponse)
def authorize_with_capability(req: CapabilityAuthorizationRequest) -> dict:
    assert _engine is not None
    intent = PaymentIntent(
        agent_id=req.agent_id, payee=req.payee, asset=req.asset, network=req.network,
        amount=req.amount, resource=req.resource,
    )
    try:
        return _engine.authorize_with_capability(
            intent,
            req.capability_id,
            load_private_key(PRIVATE_KEY_PATH),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.post("/v1/authorize/identity", response_model=AuthorizationResponse)
def authorize_with_identity(req: IdentityAuthorizationRequest) -> dict:
    assert _engine is not None
    intent = PaymentIntent(
        agent_id=req.agent_id,
        payee=req.payee,
        asset=req.asset,
        network=req.network,
        amount=req.amount,
        resource=req.resource,
        metadata=req.metadata,
        intent_id=req.intent_id,
        timestamp=req.timestamp,
    )
    try:
        return _engine.authorize_with_identity(
            intent,
            req.capability_id,
            req.identity_id,
            req.agent_signature,
            load_private_key(PRIVATE_KEY_PATH),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@app.post("/v1/actions/authorize", response_model=AuthorizationResponse)
def authorize_action(req: ActionAuthorizationRequest) -> dict:
    """Canonical protocol-agnostic authority issuance endpoint."""
    assert _engine is not None
    action = ActionIntent(
        agent_id=req.agent_id,
        action_type=req.action_type,
        target=req.target,
        resource=req.resource,
        amount=req.amount,
        asset=req.asset,
        network=req.network,
        metadata=req.metadata,
        intent_id=req.intent_id,
        timestamp=req.timestamp,
    )
    try:
        return _engine.authorize_action(
            action,
            req.capability_id,
            req.identity_id,
            req.agent_signature,
            load_private_key(PRIVATE_KEY_PATH),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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


@app.get("/v1/authority/capabilities/{capability_id}")
def authority_capability(capability_id: str) -> dict:
    """Explain the authority provenance of one capability."""
    assert _storage is not None
    try:
        explanation = AuthorityGraph(_storage).explain(capability_id)
        capability = _storage.capability(capability_id)
        if capability is not None:
            dynamic = DynamicAuthorityService(_storage).explain(
                capability.agent_id,
                capability.capability_id,
            )
            explanation["dynamic_authority"] = dynamic
        return explanation
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/governance/policy")
def governance_policy() -> dict:
    assert _governance_policy is not None
    return {
        **_governance_policy.as_dict(),
        "policy_sha256": _governance_policy.digest,
    }


@app.post(
    "/v1/authority/reset",
    response_model=AuthorityResetResponse,
)
def authority_reset(req: AuthorityResetRequest) -> dict:
    assert _storage is not None
    try:
        return AuthorityGovernanceService(_storage).reset(
            req.reset,
            load_public_key(GOVERNANCE_PUBLIC_KEY_PATH),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(
    "/v1/authority/reset/multi",
    response_model=MultiPartyAuthorityResetResponse,
)
def authority_reset_multiparty(req: MultiPartyAuthorityResetRequest) -> dict:
    assert _storage is not None and _governance_policy is not None
    if _governance_policy.threshold < 2:
        raise HTTPException(
            status_code=503,
            detail="multi-party governance policy is not configured",
        )
    try:
        return MultiPartyAuthorityGovernanceService(_storage).reset(
            req.action,
            req.approvals,
            _governance_policy,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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


@app.post(
    "/v1/policies/governed/publish",
    response_model=GovernedPolicyPublishResponse,
)
def publish_governed_policy(req: GovernedPolicyPublishRequest) -> dict:
    assert _storage is not None and _governance_policy is not None
    if _governance_policy.threshold < 2:
        raise HTTPException(
            status_code=503,
            detail="multi-party governance policy is not configured",
        )
    if "POLICY_CHANGE" not in _governance_policy.allowed_actions:
        raise HTTPException(
            status_code=403,
            detail="governance policy does not allow policy changes",
        )
    try:
        return GovernedPolicyVersionRegistry(_storage).publish(
            req.policy,
            req.governance_action,
            req.approvals,
            _governance_policy,
            load_public_key(PUBLIC_KEY_PATH),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/v1/policies/governed/{policy_sha256}")
def governed_policy(policy_sha256: str) -> dict:
    assert _storage is not None
    envelope = _storage.governed_policy_change_by_sha(policy_sha256)
    if envelope is None:
        raise HTTPException(status_code=404, detail="governed policy version not found")
    return envelope


@app.get("/v1/policies/governed/control/{policy_id}")
def governed_policy_control(policy_id: str) -> dict:
    assert _storage is not None
    control = _storage.policy_control(policy_id)
    if control is None:
        raise HTTPException(status_code=404, detail="policy control state not found")
    return control


@app.post(
    "/v1/policies/governed/freeze",
    response_model=GovernedPolicyControlResponse,
)
def freeze_governed_policy(req: GovernedPolicyControlRequest) -> dict:
    assert _storage is not None and _governance_policy is not None
    if _governance_policy.threshold < 2:
        raise HTTPException(
            status_code=503,
            detail="multi-party governance policy is not configured",
        )
    if "POLICY_FREEZE" not in _governance_policy.allowed_actions:
        raise HTTPException(
            status_code=403,
            detail="governance policy does not allow policy freeze",
        )
    try:
        action = req.governance_action
        if action.get("action") != "POLICY_FREEZE":
            raise PermissionError("unsupported policy control action")
        return GovernedPolicyControlService(_storage).apply(
            action,
            req.approvals,
            _governance_policy,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(
    "/v1/policies/governed/rollback",
    response_model=GovernedPolicyControlResponse,
)
def rollback_governed_policy(req: GovernedPolicyControlRequest) -> dict:
    assert _storage is not None and _governance_policy is not None
    if _governance_policy.threshold < 2:
        raise HTTPException(
            status_code=503,
            detail="multi-party governance policy is not configured",
        )
    if "POLICY_ROLLBACK" not in _governance_policy.allowed_actions:
        raise HTTPException(
            status_code=403,
            detail="governance policy does not allow policy rollback",
        )
    try:
        action = req.governance_action
        if action.get("action") != "POLICY_ROLLBACK":
            raise PermissionError("unsupported policy control action")
        return GovernedPolicyControlService(_storage).apply(
            action,
            req.approvals,
            _governance_policy,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/v1/policies/{policy_sha256}")
def policy_version(policy_sha256: str) -> dict:
    assert _storage is not None
    artifact = _storage.policy_version_by_sha(policy_sha256)
    if artifact is None:
        raise HTTPException(status_code=404, detail="policy version not found")
    return artifact


@app.post("/v1/verify/adversarial", response_model=AdversarialVerificationResponse)
def verify_adversarial(req: AdversarialVerificationRequest) -> dict:
    public_key = load_public_key(PUBLIC_KEY_PATH)
    authorization = req.authorization.model_dump()
    baseline_valid, baseline_reason = verify_execution_authorization(
        authorization,
        public_key,
    )
    attacks = AdversarialVerificationPlane.run(
        authorization,
        public_key,
    )
    all_blocked = all(result.passed for result in attacks)
    return {
        "baseline_valid": baseline_valid,
        "baseline_reason": baseline_reason,
        "attacks": [
            {
                "attack_id": result.attack_id,
                "passed": result.passed,
                "description": result.description,
                "reason": result.reason,
            }
            for result in attacks
        ],
        "all_blocked": all_blocked,
    }


@app.get("/v1/evidence/authorization/{authorization_id}")
def evidence_authorization(authorization_id: str) -> dict:
    assert _storage is not None
    try:
        return EvidenceGraph(
            _storage,
            load_public_key(PUBLIC_KEY_PATH),
            load_public_key(GOVERNANCE_PUBLIC_KEY_PATH),
        ).build(authorization_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/evidence/intent/{intent_id}")
def evidence_intent(intent_id: str) -> dict:
    assert _storage is not None
    try:
        return EvidenceGraph(
            _storage,
            load_public_key(PUBLIC_KEY_PATH),
            load_public_key(GOVERNANCE_PUBLIC_KEY_PATH),
        ).build_by_intent(intent_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/v1/agents/{agent_id}/history")
def history(agent_id: str, limit: int = 20) -> list[dict]:
    assert _storage is not None
    return _storage.history(agent_id, limit=limit)
