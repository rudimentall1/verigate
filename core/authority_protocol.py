"""Genesis 2.0 canonical Authority Protocol primitives.

This module defines the control-plane vocabulary without replacing the existing
proven registries and enforcement implementations. It references their exact
IDs/digests instead of copying mutable permission state.

Lifecycle:
    IDENTIFY -> PROPOSE -> VERIFY -> DECIDE -> AUTHORIZE -> ENFORCE
    -> OBSERVE -> PROVE -> LEARN
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AuthorityState(str, Enum):
    PROBATION = "PROBATION"
    LIMITED = "LIMITED"
    STANDARD = "STANDARD"
    ELEVATED = "ELEVATED"
    SUSPENDED = "SUSPENDED"


class LifecycleStage(str, Enum):
    IDENTIFY = "IDENTIFY"
    PROPOSE = "PROPOSE"
    VERIFY = "VERIFY"
    DECIDE = "DECIDE"
    AUTHORIZE = "AUTHORIZE"
    ENFORCE = "ENFORCE"
    OBSERVE = "OBSERVE"
    PROVE = "PROVE"
    LEARN = "LEARN"


@dataclass(frozen=True)
class Authority:
    """Canonical dynamic authority envelope.

    Static capability remains the hard ceiling. This object describes the
    currently effective state and the exact artifacts that produced it.
    """

    authority_id: str
    agent_id: str
    identity_id: str
    capability_id: str
    capability_version: int
    capability_sha256: str
    state: AuthorityState = AuthorityState.PROBATION
    multiplier: float = 1.0
    epoch: int = 0
    ledger_head_hash: str = ""
    effective_from: float = field(default_factory=time.time)
    expires_at: float | None = None
    parent_authority_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def digest(self) -> str:
        return canonical_digest(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "authority_id": self.authority_id,
            "agent_id": self.agent_id,
            "identity_id": self.identity_id,
            "capability_id": self.capability_id,
            "capability_version": self.capability_version,
            "capability_sha256": self.capability_sha256,
            "state": self.state.value,
            "multiplier": self.multiplier,
            "epoch": self.epoch,
            "ledger_head_hash": self.ledger_head_hash,
            "effective_from": self.effective_from,
            "expires_at": self.expires_at,
            "parent_authority_id": self.parent_authority_id,
            "evidence_refs": list(self.evidence_refs),
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class AuthorityRequest:
    """Canonical input to the Authority Control Plane.

    The request references an exact ActionIntent and its identity. It does
    not contain implicit permission; authorization is produced only after
    policy, capability and authority verification.
    """

    intent_id: str
    agent_id: str
    identity_id: str
    requested_capability: str | None = None
    parent_intent_id: str | None = None
    lifecycle_stage: LifecycleStage = LifecycleStage.PROPOSE
    requested_at: float = field(default_factory=time.time)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "intent_id": self.intent_id,
            "agent_id": self.agent_id,
            "identity_id": self.identity_id,
            "requested_capability": self.requested_capability,
            "parent_intent_id": self.parent_intent_id,
            "lifecycle_stage": self.lifecycle_stage.value,
            "requested_at": self.requested_at,
            "metadata": self.metadata,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.as_dict())


@dataclass(frozen=True)
class AuthorityTransition:
    """Evidence-bearing transition in the authority lifecycle."""

    from_state: AuthorityState
    to_state: AuthorityState
    reason: str
    evidence_refs: tuple[str, ...] = ()
    epoch: int = 0
    occurred_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict[str, Any]:
        return {
            "from_state": self.from_state.value,
            "to_state": self.to_state.value,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "epoch": self.epoch,
            "occurred_at": self.occurred_at,
        }


def canonical_digest(payload: dict[str, Any]) -> str:
    """Return the protocol's deterministic SHA-256 representation."""
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def authority_ceiling_allows(
    static_limit: float,
    multiplier: float,
    requested_amount: float,
) -> bool:
    """Enforce the Genesis invariant: dynamic authority never widens scope."""
    if static_limit < 0 or multiplier < 0 or multiplier > 1.0 or requested_amount < 0:
        return False
    return requested_amount <= static_limit * multiplier
