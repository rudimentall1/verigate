"""Independent historical verification of Verigate authority decisions."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from attest.receipt import verify_execution_authorization
from .authority_state import AuthorityPolicy, AuthorityState


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def policy_window_seconds(payload: dict[str, Any], policy_artifact: dict[str, Any]) -> float:
    value = policy_artifact.get("window_seconds")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError("invalid authority policy window")
    return float(value)


def replay_authority_decision(storage, authorization: dict[str, Any], public_key) -> tuple[bool, str, dict[str, Any]]:
    """Verify that an authorization still points to an intact historical ledger head."""
    payload = authorization.get("payload", {})
    agent_id = payload.get("agent_id")
    capability_id = payload.get("capability_id")
    expected_head = payload.get("authority_ledger_head_hash")
    if not agent_id or not capability_id or not isinstance(expected_head, str):
        return False, "authorization has no historical authority binding", {}
    valid_ledger, reason = storage.verify_authority_ledger(agent_id, capability_id)
    if not valid_ledger:
        return False, reason, {"ledger_valid": False}
    rows = storage.authority_ledger(agent_id, capability_id)
    committed = []
    if expected_head != "0" * 64:
        for row in rows:
            committed.append(row)
            if row["event_hash"] == expected_head:
                break
        if not committed or committed[-1]["event_hash"] != expected_head:
            return False, "historical authority ledger head not found", {
                "ledger_valid": True, "expected_head": expected_head,
                "actual_head": rows[-1]["event_hash"] if rows else "0" * 64,
            }
    auth_valid, auth_reason = verify_execution_authorization(authorization, public_key)
    if not auth_valid:
        return False, auth_reason, {"ledger_valid": True, "head_match": True}

    snapshot = payload.get("authority_state")
    snapshot_digest = payload.get("authority_state_sha256")
    if not isinstance(snapshot, dict) or not isinstance(snapshot_digest, str):
        return False, "authorization has no authority snapshot binding", {
            "ledger_valid": True, "head_match": True,
        }
    if hashlib.sha256(_canonical(snapshot)).hexdigest() != snapshot_digest:
        return False, "authority snapshot digest mismatch", {
            "ledger_valid": True, "head_match": True,
        }
    if snapshot.get("ledger_head_hash") != expected_head:
        return False, "authority snapshot is bound to a different ledger head", {
            "ledger_valid": True, "head_match": True,
        }

    policy_artifact = payload.get("authority_policy")
    policy_digest = payload.get("authority_policy_sha256")
    if not isinstance(policy_artifact, dict) or not isinstance(policy_digest, str):
        return False, "authorization has no authority policy binding", {
            "ledger_valid": True, "head_match": True, "snapshot_valid": True,
        }
    try:
        policy = AuthorityPolicy.from_dict(policy_artifact)
    except (KeyError, TypeError, ValueError):
        return False, "invalid authority policy binding", {
            "ledger_valid": True, "head_match": True, "snapshot_valid": True,
        }
    if policy.digest != policy_digest:
        return False, "authority policy digest mismatch", {
            "ledger_valid": True, "head_match": True, "snapshot_valid": True,
        }
    if snapshot.get("authority_policy_sha256") != policy_digest:
        return False, "authority snapshot is bound to a different authority policy", {
            "ledger_valid": True, "head_match": True, "snapshot_valid": True,
        }

    evaluated_at = snapshot.get("evaluated_at")
    history_start_at = snapshot.get("history_start_at")
    if isinstance(evaluated_at, bool) or not isinstance(evaluated_at, (int, float)):
        return False, "authority snapshot has no valid evaluation timestamp", {
            "ledger_valid": True, "head_match": True, "snapshot_valid": True,
        }
    if isinstance(history_start_at, bool) or not isinstance(history_start_at, (int, float)):
        return False, "authority snapshot has no valid history boundary", {
            "ledger_valid": True, "head_match": True, "snapshot_valid": True,
        }
    try:
        expected_history_start = evaluated_at - policy_window_seconds(payload, policy_artifact)
    except ValueError:
        return False, "invalid authority policy window", {
            "ledger_valid": True, "head_match": True, "snapshot_valid": True,
        }
    reset = storage.latest_authority_reset(agent_id, capability_id)
    if reset is not None:
        expected_history_start = max(expected_history_start, float(reset["payload"]["issued_at"]))
    if history_start_at != expected_history_start:
        return False, "authority snapshot history boundary is inconsistent with policy/reset", {
            "ledger_valid": True, "head_match": True, "snapshot_valid": True,
        }
    historical_events = [
        row["event"]
        for row in committed
        if history_start_at <= float(row["event"].get("occurred_at", 0)) <= evaluated_at
    ]
    successes = sum(1 for event in historical_events if event.get("event_type") == "EXECUTION_CONFIRMED")
    adverse_types = {"EXECUTION_FAILED", "AUTHORIZATION_REJECTED", "POLICY_VIOLATION", "TAMPER_DETECTED"}
    critical_types = {"TAMPER_DETECTED", "POLICY_VIOLATION"}
    adverse = sum(1 for event in historical_events if event.get("event_type") in adverse_types)
    critical = sum(1 for event in historical_events if event.get("event_type") in critical_types)
    if (snapshot.get("successes"), snapshot.get("adverse_events"), snapshot.get("critical_events")) != (successes, adverse, critical):
        return False, "authority snapshot counters do not match historical ledger window", {
            "ledger_valid": True, "head_match": True, "snapshot_valid": True,
        }
    if snapshot.get("state") == AuthorityState.SUSPENDED.value and critical < policy.suspension_critical_events:
        return False, "authority snapshot state is not justified by historical critical events", {
            "ledger_valid": True, "head_match": True,
        }
    expected_multiplier = policy.multiplier(AuthorityState(snapshot["state"]))
    if snapshot.get("multiplier") != expected_multiplier:
        return False, "authority snapshot multiplier is inconsistent with authority policy", {
            "ledger_valid": True, "head_match": True,
        }

    return True, "historical authority decision verified", {
        "ledger_valid": True,
        "head_match": True,
        "snapshot_valid": True,
        "ledger_sequence": len(committed),
        "live_ledger_sequence": len(rows),
        "authority_state": snapshot,
        "authority_multiplier": snapshot.get("multiplier"),
        "ledger_head_hash": expected_head,
        "historical_events": historical_events,
    }
