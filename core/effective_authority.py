"""Deterministic effective authority: the intersection of every authority ceiling."""
from __future__ import annotations

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
