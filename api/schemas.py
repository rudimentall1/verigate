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


class CapabilityAuthorizationRequest(PaymentIntentRequest):
    capability_id: str = Field(..., min_length=1, examples=["cap-trader-001"])


class ActionAuthorizationRequest(BaseModel):
    identity_id: str = Field(..., min_length=1)
    capability_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_signature: str = Field(..., min_length=1)
    intent_id: str = Field(..., min_length=1)
    timestamp: float
    action_type: str = Field(..., min_length=1, examples=["mcp.tool.call"])
    target: str = Field(..., min_length=1, examples=["github.create_issue"])
    resource: str = ""
    amount: float | None = Field(None, gt=0)
    asset: str | None = None
    network: str | None = None
    metadata: dict = Field(default_factory=dict)


class IdentityAuthorizationRequest(BaseModel):
    identity_id: str = Field(..., min_length=1)
    capability_id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    agent_signature: str = Field(..., min_length=1)
    intent_id: str = Field(..., min_length=1)
    timestamp: float
    payee: str = Field(..., min_length=1)
    asset: str = Field(..., min_length=1)
    network: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    resource: str = ""
    metadata: dict = Field(default_factory=dict)


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


class DecisionReceiptResponse(BaseModel):
    payload: dict
    signature: str
    algorithm: str = "Ed25519"


class ExecutionAuthorizationResponse(BaseModel):
    payload: dict
    signature: str
    algorithm: str = "Ed25519"


class AuthorizationResponse(BaseModel):
    decision_receipt: DecisionReceiptResponse
    execution_authorization: ExecutionAuthorizationResponse | None = None


class AdversarialVerificationRequest(BaseModel):
    authorization: ExecutionAuthorizationResponse


class AdversarialAttackResponse(BaseModel):
    attack_id: str
    passed: bool
    description: str
    reason: str


class AdversarialVerificationResponse(BaseModel):
    baseline_valid: bool
    baseline_reason: str
    attacks: list[AdversarialAttackResponse]
    all_blocked: bool


class AuthorityResetRequest(BaseModel):
    reset: dict


class MultiPartyAuthorityResetRequest(BaseModel):
    action: dict
    approvals: list[dict]


class AuthorityResetResponse(BaseModel):
    reset: dict
    snapshot: dict
    snapshot_sha256: str


class MultiPartyAuthorityResetResponse(BaseModel):
    reset: dict
    snapshot: dict
    snapshot_sha256: str
    governance_policy_sha256: str


class GovernedPolicyPublishRequest(BaseModel):
    policy: dict
    governance_action: dict
    approvals: list[dict]


class GovernedPolicyPublishResponse(BaseModel):
    policy: dict
    governance_action: dict
    approvals: list[dict]
    governance_policy_sha256: str


class GovernedPolicyControlRequest(BaseModel):
    governance_action: dict
    approvals: list[dict]


class GovernedPolicyControlResponse(BaseModel):
    policy_id: str
    active_policy_sha256: str
    frozen: bool
    governance_action: dict
    approvals: list[dict]
    governance_policy_sha256: str


class ExecutionConsumeRequest(BaseModel):
    authorization: ExecutionAuthorizationResponse


class ExecutionConsumeResponse(BaseModel):
    execute: bool
    reason: str
