"""Core data models. Standard library only — no pydantic, no FastAPI.

Keeping this layer dependency-free means the decision engine can be unit
tested, embedded in another service, or ported to a different web framework
without dragging the API layer along.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Decision(str, Enum):
    ALLOW = "ALLOW"
    WARN = "WARN"
    BLOCK = "BLOCK"


class Severity(str, Enum):
    BLOCK = "BLOCK"
    WARN = "WARN"


@dataclass(frozen=True)
class PaymentIntent:
    """A single agent-initiated payment, already normalized regardless of
    the wire protocol it arrived on (x402 header, AP2 mandate, a plain
    API call, ...). Building a normalizer for a new rail means producing
    one of these — the engine never needs to know the rail existed.
    """

    agent_id: str
    payee: str
    asset: str  # e.g. "USDC"
    network: str  # e.g. "base", "ethereum", "solana"
    amount: float  # in `asset` units, already decimal-adjusted
    resource: str = ""  # what is being paid for (URL, SKU, invoice id...)
    metadata: dict[str, Any] = field(default_factory=dict)
    intent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)


    def as_action_intent(self) -> "ActionIntent":
        """Normalize a payment into the protocol-agnostic action model."""
        return ActionIntent(
            agent_id=self.agent_id,
            action_type="payment",
            target=self.payee,
            resource=self.resource,
            amount=self.amount,
            asset=self.asset,
            network=self.network,
            metadata=self.metadata,
            intent_id=self.intent_id,
            timestamp=self.timestamp,
        )


@dataclass(frozen=True)
class ActionIntent:
    """Protocol-agnostic authorization request from an autonomous agent.

    PaymentIntent remains the payment-specific compatibility model. New
    integrations can normalize consequential tool/API/cloud/wallet actions
    into ActionIntent without coupling the authorization protocol to one rail.
    """

    agent_id: str
    action_type: str
    target: str
    resource: str = ""
    amount: float | None = None
    asset: str | None = None
    network: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    intent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "agent_id": self.agent_id,
            "action_type": self.action_type,
            "target": self.target,
            "resource": self.resource,
            "amount": self.amount,
            "asset": self.asset,
            "network": self.network,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class RuleMatch:
    rule_id: str
    severity: Severity
    message: str


@dataclass(frozen=True)
class GuardrailDecision:
    intent_id: str
    agent_id: str
    decision: Decision
    matched_rules: tuple[RuleMatch, ...]
    evaluated_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "agent_id": self.agent_id,
            "decision": self.decision.value,
            "matched_rules": [
                {"rule": m.rule_id, "severity": m.severity.value, "message": m.message}
                for m in self.matched_rules
            ],
            "evaluated_at": self.evaluated_at,
        }
