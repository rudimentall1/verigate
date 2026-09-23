"""Core data models. Standard library only — no pydantic, no FastAPI.

Keeping this layer dependency-free means the decision engine can be unit
tested, embedded in another service, or ported to a different web framework
without dragging the API layer along.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Decision(str, Enum):
    """Authorization outcome.

    WARN is a human-review state: it never grants execution permission.
    BLOCK is a hard deny enforced by the execution boundary.
    """
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
class AgentIdentity:
    """Canonical identity of an autonomous principal.

    This is intentionally descriptive rather than a credential store. The
    execution layer must bind concrete credentials/wallets to this identity
    before side effects are permitted.
    """

    agent_id: str
    organization_id: str = ""
    identity_version: int = 1
    reputation_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Capability:
    """Programmable authority granted to an agent."""

    capability_id: str
    agent_id: str
    allowed_actions: tuple[str, ...] = ()
    allowed_targets: tuple[str, ...] = ()
    allowed_resources: tuple[str, ...] = ()
    allowed_networks: tuple[str, ...] = ()
    allowed_assets: tuple[str, ...] = ()
    max_per_action: dict[str, float] = field(default_factory=dict)
    aggregate_limits: dict[str, float] = field(default_factory=dict)
    conditions: tuple[str, ...] = ()
    version: int = 1
    issued_at: float = field(default_factory=time.time)
    expires_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def digest(self) -> str:
        """Stable fingerprint of the exact capability definition."""
        payload = {
            "capability_id": self.capability_id,
            "agent_id": self.agent_id,
            "allowed_actions": self.allowed_actions,
            "allowed_targets": self.allowed_targets,
            "allowed_resources": self.allowed_resources,
            "allowed_networks": self.allowed_networks,
            "allowed_assets": self.allowed_assets,
            "max_per_action": self.max_per_action,
            "aggregate_limits": self.aggregate_limits,
            "conditions": self.conditions,
            "version": self.version,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "metadata": self.metadata,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def permits(self, action: "ActionIntent", now: float | None = None) -> tuple[bool, str]:
        """Check the static scope of this capability against one action."""
        now = time.time() if now is None else now
        if action.agent_id != self.agent_id:
            return False, "capability agent mismatch"
        if self.expires_at is not None and now >= self.expires_at:
            return False, "capability expired"
        if self.allowed_actions and action.action_type not in self.allowed_actions:
            return False, "action type outside capability"
        if self.allowed_targets and action.target not in self.allowed_targets:
            return False, "target outside capability"
        if self.allowed_resources and action.resource not in self.allowed_resources:
            return False, "resource outside capability"
        if self.allowed_networks and (action.network not in self.allowed_networks):
            return False, "network outside capability"
        if self.allowed_assets and (action.asset not in self.allowed_assets):
            return False, "asset outside capability"
        limit = self.max_per_action.get(action.asset or "")
        if limit is not None and (action.amount is None or action.amount > limit):
            return False, "action exceeds capability limit"
        return True, "capability permits action"


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
