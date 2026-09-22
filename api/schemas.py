from __future__ import annotations

from pydantic import BaseModel, Field


class PaymentIntentRequest(BaseModel):
    agent_id: str = Field(..., examples=["trading-agent-001"])
    payee: str = Field(..., examples=["0xMerchant123"])
    asset: str = Field(..., examples=["USDC"])
    network: str = Field(..., examples=["base"])
    amount: float = Field(..., gt=0, examples=[10.5])
    resource: str = Field("", examples=["https://api.example.com/data"])
    sign: bool = Field(True, description="Return an Ed25519-signed attestation")


class X402HeaderRequest(BaseModel):
    agent_id: str
    payment_required_header: str = Field(
        ..., description="Base64-encoded x402 PAYMENT-REQUIRED header value"
    )
    sign: bool = True


class RuleMatchResponse(BaseModel):
    rule: str
    severity: str
    message: str


class DecisionResponse(BaseModel):
    intent_id: str
    agent_id: str
    decision: str
    matched_rules: list[RuleMatchResponse]
    evaluated_at: float


class AttestationResponse(BaseModel):
    payload: DecisionResponse
    signature: str
    algorithm: str = "Ed25519"


class VerifyRequest(BaseModel):
    payload: dict
    signature: str
    algorithm: str = "Ed25519"


class VerifyResponse(BaseModel):
    valid: bool
    reason: str


class AuthorizationReceiptResponse(BaseModel):
    payload: dict
    signature: str
    algorithm: str = "Ed25519"
