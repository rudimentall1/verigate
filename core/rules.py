"""Deterministic rule evaluators. Every check here is something you can
verify by reading the policy file — no statistical scores, no "reputation"
numbers pulled from an unverifiable data source.
"""
from __future__ import annotations

from .models import ActionIntent, PaymentIntent, RuleMatch, Severity
from .policy import Policy


def check_action_type_allowed(intent: ActionIntent, policy: Policy) -> RuleMatch | None:
    allowed = policy.allowed_action_types
    if allowed is None:
        return None
    if intent.action_type.lower() not in {a.lower() for a in allowed}:
        return RuleMatch(
            "action_type_not_allowed",
            Severity.BLOCK,
            f"action type '{intent.action_type}' is not allowed by policy",
        )
    return None


def check_purpose_allowed(intent: ActionIntent, policy: Policy) -> RuleMatch | None:
    allowed = policy.allowed_purposes
    if allowed is None:
        return None
    purpose = intent.purpose.strip()
    if purpose.lower() not in {p.strip().lower() for p in allowed}:
        return RuleMatch(
            "purpose_not_allowed",
            Severity.BLOCK,
            f"purpose '{purpose}' is not allowed by policy",
        )
    return None


def check_context_constraints(intent: ActionIntent, policy: Policy) -> RuleMatch | None:
    constraints = policy.context_constraints
    if not constraints:
        return None
    context = intent.declared_context or {}
    for key, expected in constraints.items():
        actual = context.get(key)
        if isinstance(expected, list):
            if actual not in expected:
                return RuleMatch(
                    "context_not_allowed", Severity.BLOCK,
                    f"context '{key}' value '{actual}' is not allowed by policy",
                )
        elif actual != expected:
            return RuleMatch(
                "context_not_allowed", Severity.BLOCK,
                f"context '{key}' does not match policy constraint",
            )
    return None


def check_execution_graph(intent: ActionIntent, policy: Policy) -> RuleMatch | None:
    """Enforce the declared execution path as a deterministic policy boundary.

    The graph is part of the signed ActionIntent, so a valid signature does
    not grant permission to route through an unapproved module, hook, router,
    or target. Missing graph data is denied when a graph policy is configured.
    """
    expected = policy.execution_graph
    if not expected:
        return None
    metadata = intent.metadata or {}
    actual = metadata.get("execution_graph")
    if not isinstance(actual, dict):
        return RuleMatch(
            "execution_graph_missing",
            Severity.BLOCK,
            "execution graph is required by policy",
        )
    for key, value in expected.items():
        if actual.get(key) != value:
            return RuleMatch(
                "execution_graph_not_allowed",
                Severity.BLOCK,
                f"execution graph field '{key}' is not allowed by policy",
            )
    return None


def _action_destination(intent: ActionIntent) -> str | None:
    """Return the execution destination carried by the signed action."""
    metadata = intent.metadata or {}
    destination = metadata.get("destination")
    if isinstance(destination, str) and destination.strip():
        return destination.strip()
    invocation = metadata.get("tool_invocation")
    if isinstance(invocation, dict):
        destination = invocation.get("destination")
        if isinstance(destination, str) and destination.strip():
            return destination.strip()
    return None


def check_destination_allowed(intent: ActionIntent, policy: Policy) -> RuleMatch | None:
    """Fail closed on destinations outside the configured egress scope."""
    if policy.allowed_destinations is None and not policy.blocked_destinations:
        return None
    destination = _action_destination(intent)
    if destination is None:
        return RuleMatch(
            "destination_missing",
            Severity.BLOCK,
            "execution destination is required by policy",
        )
    lowered = destination.lower()
    if lowered in {d.lower() for d in policy.blocked_destinations}:
        return RuleMatch(
            "destination_blocked",
            Severity.BLOCK,
            f"destination '{destination}' is blocked by policy",
        )
    if policy.allowed_destinations is not None and lowered not in {d.lower() for d in policy.allowed_destinations}:
        return RuleMatch(
            "destination_not_allowed",
            Severity.BLOCK,
            f"destination '{destination}' is outside the allowed execution scope",
        )
    return None


def check_target_allowed(intent: ActionIntent, policy: Policy) -> RuleMatch | None:
    blocked = {p.lower() for p in policy.blocked_payees}
    if intent.target.lower() in blocked:
        return RuleMatch(
            "target_blocked",
            Severity.BLOCK,
            f"target '{intent.target}' is blocked by policy",
        )
    allowed = policy.allowed_targets
    if allowed is not None and intent.target.lower() not in {t.lower() for t in allowed}:
        return RuleMatch(
            "target_not_allowed",
            Severity.BLOCK,
            f"target '{intent.target}' is not allowed by policy",
        )
    return None


def check_generic_network_allowed(intent: ActionIntent, policy: Policy) -> RuleMatch | None:
    if intent.network is None or policy.allowed_networks is None:
        return None
    if intent.network.lower() not in {n.lower() for n in policy.allowed_networks}:
        return RuleMatch(
            "network_not_allowed",
            Severity.BLOCK,
            f"network '{intent.network}' is not allowed by policy",
        )
    return None


def check_generic_asset_allowed(intent: ActionIntent, policy: Policy) -> RuleMatch | None:
    if intent.asset is None or policy.allowed_assets is None:
        return None
    if intent.asset.upper() not in {a.upper() for a in policy.allowed_assets}:
        return RuleMatch(
            "asset_not_allowed",
            Severity.BLOCK,
            f"asset '{intent.asset}' is not allowed by policy",
        )
    return None


def check_generic_amount_cap(intent: ActionIntent, policy: Policy) -> RuleMatch | None:
    if intent.amount is None or intent.asset is None:
        return None
    cap = policy.per_tx_cap.get(intent.asset.upper())
    if cap is not None and intent.amount > cap:
        return RuleMatch(
            "per_tx_cap_exceeded",
            Severity.BLOCK,
            f"amount {intent.amount} {intent.asset} exceeds per-transaction cap {cap}",
        )
    return None


def check_blocked_payee(intent: PaymentIntent, policy: Policy) -> RuleMatch | None:
    if intent.payee.lower() in {p.lower() for p in policy.blocked_payees}:
        return RuleMatch("blocked_payee", Severity.BLOCK, f"payee '{intent.payee}' is on the blocklist")
    return None


def check_payee_allowlist(intent: PaymentIntent, policy: Policy) -> RuleMatch | None:
    if policy.allowed_payees is None:
        return None
    if intent.payee.lower() not in {p.lower() for p in policy.allowed_payees}:
        return RuleMatch(
            "payee_not_allowlisted",
            Severity.BLOCK,
            f"payee '{intent.payee}' is not on the allowlist",
        )
    return None


def check_network_allowed(intent: PaymentIntent, policy: Policy) -> RuleMatch | None:
    if policy.allowed_networks is None:
        return None
    if intent.network.lower() not in {n.lower() for n in policy.allowed_networks}:
        return RuleMatch(
            "network_not_allowed",
            Severity.BLOCK,
            f"network '{intent.network}' is not in allowed_networks",
        )
    return None


def check_asset_allowed(intent: PaymentIntent, policy: Policy) -> RuleMatch | None:
    if policy.allowed_assets is None:
        return None
    if intent.asset.upper() not in {a.upper() for a in policy.allowed_assets}:
        return RuleMatch(
            "asset_not_allowed",
            Severity.BLOCK,
            f"asset '{intent.asset}' is not in allowed_assets",
        )
    return None


def check_per_tx_cap(intent: PaymentIntent, policy: Policy) -> RuleMatch | None:
    cap = policy.per_tx_cap.get(intent.asset.upper())
    if cap is not None and intent.amount > cap:
        return RuleMatch(
            "per_tx_cap_exceeded",
            Severity.BLOCK,
            f"amount {intent.amount} {intent.asset} exceeds per-transaction cap {cap}",
        )
    return None


def check_new_payee_cap(
    intent: PaymentIntent, policy: Policy, payee_seen_before: bool
) -> RuleMatch | None:
    if payee_seen_before:
        return None
    cap = policy.new_payee_cap.get(intent.asset.upper())
    if cap is not None and intent.amount > cap:
        return RuleMatch(
            "new_payee_cap_exceeded",
            Severity.WARN,
            f"first payment to '{intent.payee}': amount {intent.amount} {intent.asset} "
            f"exceeds new-payee cap {cap} — needs confirmation",
        )
    return None


def check_daily_cap(
    intent: PaymentIntent, policy: Policy, spent_today: float
) -> RuleMatch | None:
    cap = policy.daily_cap.get(intent.asset.upper())
    if cap is not None and (spent_today + intent.amount) > cap:
        return RuleMatch(
            "daily_cap_exceeded",
            Severity.WARN,
            f"would bring today's total to {spent_today + intent.amount:.2f} {intent.asset}, "
            f"exceeding daily cap {cap}",
        )
    return None


def check_confirmation_threshold(intent: PaymentIntent, policy: Policy) -> RuleMatch | None:
    threshold = policy.confirmation_required_over.get(intent.asset.upper())
    if threshold is not None and intent.amount > threshold:
        return RuleMatch(
            "confirmation_required",
            Severity.WARN,
            f"amount {intent.amount} {intent.asset} exceeds confirmation threshold {threshold}",
        )
    return None


def check_rate_limit(policy: Policy, calls_last_minute: int) -> RuleMatch | None:
    if policy.rate_limit_per_minute and calls_last_minute >= policy.rate_limit_per_minute:
        return RuleMatch(
            "rate_limit_exceeded",
            Severity.BLOCK,
            f"{calls_last_minute} payments in the last minute exceeds limit "
            f"{policy.rate_limit_per_minute}",
        )
    return None
