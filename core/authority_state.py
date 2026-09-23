"""Deterministic dynamic authority derived from verified agent outcomes.

Dynamic authority never expands beyond a registered Capability. It starts
conservatively, promotes only after verified successes, and suspends on
critical authority failures. The resulting snapshot is bound to execution
authorization so later state changes cannot mutate already-issued authority.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .models import ActionIntent, Capability
from .storage import Storage


class AuthorityState(str, Enum):
    PROBATION = "PROBATION"
    LIMITED = "LIMITED"
    STANDARD = "STANDARD"
    ELEVATED = "ELEVATED"
    SUSPENDED = "SUSPENDED"


@dataclass(frozen=True)
class AuthorityPolicy:
    """Deterministic thresholds; never a statistical risk score."""

    window_seconds: int = 30 * 24 * 3600
    probation_successes: int = 5
    standard_successes: int = 20
    limited_adverse_events: int = 2
    suspension_critical_events: int = 1
    probation_multiplier: float = 0.10
    limited_multiplier: float = 0.25
    standard_multiplier: float = 0.50
    elevated_multiplier: float = 1.00
    elevated_only_actions: tuple[str, ...] = ("irreversible_operation",)

    def multiplier(self, state: AuthorityState) -> float:
        return {
            AuthorityState.PROBATION: self.probation_multiplier,
            AuthorityState.LIMITED: self.limited_multiplier,
            AuthorityState.STANDARD: self.standard_multiplier,
            AuthorityState.ELEVATED: self.elevated_multiplier,
            AuthorityState.SUSPENDED: 0.0,
        }[state]


@dataclass(frozen=True)
class AuthoritySnapshot:
    agent_id: str
    capability_id: str
    state: AuthorityState
    successes: int
    adverse_events: int
    critical_events: int
    multiplier: float
    evaluated_at: float = field(default_factory=time.time)
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "capability_id": self.capability_id,
            "state": self.state.value,
            "successes": self.successes,
            "adverse_events": self.adverse_events,
            "critical_events": self.critical_events,
            "multiplier": self.multiplier,
            "evaluated_at": self.evaluated_at,
            "reason": self.reason,
        }

    @property
    def digest(self) -> str:
        canonical = json.dumps(
            self.as_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


class DynamicAuthorityService:
    """Compute and enforce the current effective authority for one capability."""
    SUCCESS_EVENTS = frozenset({"EXECUTION_CONFIRMED"})
    ADVERSE_EVENTS = frozenset({
        "EXECUTION_FAILED",
        "AUTHORIZATION_REJECTED",
        "POLICY_VIOLATION",
        "TAMPER_DETECTED",
    })
    CRITICAL_EVENTS = frozenset({"TAMPER_DETECTED", "POLICY_VIOLATION"})

    def __init__(self, storage: Storage, policy: AuthorityPolicy | None = None):
        self.storage = storage
        self.policy = policy or AuthorityPolicy()

    def snapshot(
        self,
        agent_id: str,
        capability_id: str,
        *,
        now: float | None = None,
    ) -> AuthoritySnapshot:
        now = time.time() if now is None else now
        events = self.storage.authority_events(
            agent_id=agent_id,
            capability_id=capability_id,
            since=now - self.policy.window_seconds,
        )
        successes = sum(1 for event in events if event["event_type"] in self.SUCCESS_EVENTS)
        adverse = sum(1 for event in events if event["event_type"] in self.ADVERSE_EVENTS)
        critical = sum(1 for event in events if event["event_type"] in self.CRITICAL_EVENTS)

        previous = self.storage.latest_authority_state(agent_id, capability_id)
        if previous == AuthorityState.SUSPENDED.value:
            state = AuthorityState.SUSPENDED
            reason = "suspended until an explicit authority reset"
        elif critical >= self.policy.suspension_critical_events:
            state = AuthorityState.SUSPENDED
            reason = "critical authority event observed"
        elif adverse >= self.policy.limited_adverse_events:
            state = AuthorityState.LIMITED
            reason = "adverse outcome threshold reached"
        elif successes >= self.policy.standard_successes and adverse <= 1:
            state = AuthorityState.ELEVATED
            reason = "verified success threshold reached with bounded adverse history"
        elif successes >= self.policy.probation_successes and adverse <= 1:
            state = AuthorityState.STANDARD
            reason = "probation success threshold reached"
        else:
            state = AuthorityState.PROBATION
            reason = "insufficient verified history for broader authority"

        snapshot = AuthoritySnapshot(
            agent_id=agent_id,
            capability_id=capability_id,
            state=state,
            successes=successes,
            adverse_events=adverse,
            critical_events=critical,
            multiplier=self.policy.multiplier(state),
            evaluated_at=now,
            reason=reason,
        )
        self.storage.set_authority_state(
            agent_id,
            capability_id,
            state.value,
            snapshot.as_dict(),
        )
        return snapshot

    def assert_action(self, capability: Capability, action: ActionIntent) -> AuthoritySnapshot:
        """Fail closed when current dynamic authority does not permit the action."""
        snapshot = self.snapshot(action.agent_id, capability.capability_id)
        if snapshot.state == AuthorityState.SUSPENDED:
            raise PermissionError("dynamic authority is suspended")

        if action.action_type in self.policy.elevated_only_actions and snapshot.state != AuthorityState.ELEVATED:
            raise PermissionError("action requires elevated dynamic authority")

        if action.amount is not None:
            base_limit = capability.max_per_action.get(action.asset or "")
            if base_limit is not None:
                effective_limit = base_limit * snapshot.multiplier
                if action.amount > effective_limit:
                    raise PermissionError("action exceeds dynamic authority limit")

        return snapshot

    def record_event(
        self,
        *,
        agent_id: str,
        capability_id: str,
        event_type: str,
        evidence_ref: str,
        action_type: str | None = None,
        identity_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: float | None = None,
    ) -> dict[str, Any]:
        if not event_type or not evidence_ref:
            raise ValueError("event_type and evidence_ref are required")
        if event_type not in self.SUCCESS_EVENTS | self.ADVERSE_EVENTS:
            raise ValueError("unknown authority event type")
        event = {
            "event_id": hashlib.sha256(
                f"{agent_id}:{capability_id}:{event_type}:{evidence_ref}".encode("utf-8")
            ).hexdigest(),
            "agent_id": agent_id,
            "capability_id": capability_id,
            "identity_id": identity_id,
            "event_type": event_type,
            "action_type": action_type,
            "evidence_ref": evidence_ref,
            "metadata": metadata or {},
            "occurred_at": time.time() if occurred_at is None else occurred_at,
        }
        self.storage.record_authority_event(event)
        return event

    def explain(self, agent_id: str, capability_id: str) -> dict[str, Any]:
        snapshot = self.snapshot(agent_id, capability_id)
        return {
            "snapshot": snapshot.as_dict(),
            "snapshot_sha256": snapshot.digest,
            "events": self.storage.authority_events(
                agent_id=agent_id,
                capability_id=capability_id,
                since=time.time() - self.policy.window_seconds,
            ),
        }
