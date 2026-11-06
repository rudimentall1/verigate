"""Deterministic effective authority: the intersection of every authority ceiling."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .authority_state import AuthoritySnapshot
from .models import ActionIntent, Capability
from .policy import Policy


def _intersect(parent: tuple[str, ...], policy: list[str] | None) -> list[str] | None:
    if parent and policy is not None:
        return [value for value in parent if value in policy]
    if parent:
        return list(parent)
    if policy is not None:
        return list(policy)
    return None


def _context_intersection(capability: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in set(capability) | set(policy):
        if key not in capability:
            result[key] = policy[key]
            continue
        if key not in policy:
            result[key] = capability[key]
            continue
        cap = capability[key]
        pol = policy[key]
        if isinstance(cap, (list, tuple, set)) and isinstance(pol, (list, tuple, set)):
            result[key] = [value for value in cap if value in pol]
        elif isinstance(cap, (list, tuple, set)):
            result[key] = [value for value in cap if value == pol]
        elif isinstance(pol, (list, tuple, set)):
            result[key] = [cap] if cap in pol else []
        elif cap == pol:
            result[key] = cap
        else:
            result[key] = []
    return result


def _finite_decimal(value: Any) -> Decimal | None:
    """Normalize numeric values crossing JSON boundaries without float comparisons."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def verify_effective_action(action: dict[str, Any], authority: dict[str, Any]) -> tuple[bool, str]:
    """Enforce the signed effective ceiling at the execution boundary."""
    for field in ("action_type", "target", "resource", "network", "asset"):
        allowed = authority.get(field)
        if allowed and action.get(field) not in allowed:
            return False, f"execution action outside effective {field} authority"
    purposes = authority.get("purpose")
    if purposes and action.get("purpose", "").lower() not in {str(p).lower() for p in purposes}:
        return False, "execution purpose outside effective authority"
    for key, expected in authority.get("context_constraints", {}).items():
        actual = (action.get("declared_context") or {}).get(key)
        if isinstance(expected, list):
            if actual not in expected:
                return False, f"execution context '{key}' outside effective authority"
        elif actual != expected:
            return False, f"execution context '{key}' outside effective authority"

    limits = authority.get("per_action_limits", {})
    asset = action.get("asset")
    if asset in limits:
        raw_amount = action.get("amount")
        raw_exact = action.get("amount_exact")
        # ActionIntent signs both the compatibility amount and its exact
        # decimal form. Refuse missing or divergent representations rather
        # than accidentally checking one amount while executing another.
        if (raw_amount is None) != (raw_exact is None):
            return False, "authorized amount and exact amount do not match"
        amount = _finite_decimal(raw_exact if raw_exact is not None else raw_amount)
        compatibility_amount = _finite_decimal(raw_amount)
        limit = _finite_decimal(limits[asset])
        if (
            amount is None
            or compatibility_amount is None
            or limit is None
            or amount < 0
            or limit < 0
            or amount != compatibility_amount
            or amount > limit
        ):
            return False, "execution amount exceeds effective authority"
    return True, "execution action is within effective authority"


def effective_authority(
    action: ActionIntent,
    capability: Capability,
    policy: Policy,
    authority: AuthoritySnapshot,
) -> dict[str, Any]:
    """Return a deterministic, non-expandable authority snapshot for execution."""
    return {
        "action_type": _intersect(capability.allowed_actions, policy.allowed_action_types),
        "purpose": _intersect(capability.allowed_purposes, policy.allowed_purposes),
        "target": _intersect(capability.allowed_targets, policy.allowed_targets),
        "resource": list(capability.allowed_resources),
        "network": _intersect(capability.allowed_networks, policy.allowed_networks),
        "asset": _intersect(capability.allowed_assets, policy.allowed_assets),
        "context_constraints": _context_intersection(
            capability.context_constraints,
            policy.context_constraints,
        ),
        "per_action_limits": {
            asset: min(
                limit,
                policy.per_tx_cap.get(asset, limit),
                limit * authority.multiplier,
            )
            for asset, limit in capability.max_per_action.items()
        },
        "requested_constraints": action.constraints,
        "authority_state": authority.state.value,
        "authority_multiplier": authority.multiplier,
    }
