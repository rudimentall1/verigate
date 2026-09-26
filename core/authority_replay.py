"""Independent historical verification of Verigate authority decisions."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from attest.receipt import verify_execution_authorization
from .authority_state import AuthorityPolicy, AuthorityState


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


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

    historical_events = [row["event"] for row in committed]
    successes = sum(1 for event in historical_events if event.get("event_type") == "EXECUTION_CONFIRMED")
    adverse_types = {"EXECUTION_FAILED", "AUTHORIZATION_REJECTED", "POLICY_VIOLATION", "TAMPER_DETECTED"}
    critical_types = {"TAMPER_DETECTED", "POLICY_VIOLATION"}
    adverse = sum(1 for event in historical_events if event.get("event_type") in adverse_types)
    critical = sum(1 for event in historical_events if event.get("event_type") in critical_types)
    if (snapshot.get("successes"), snapshot.get("adverse_events"), snapshot.get("critical_events")) != (successes, adverse, critical):
        return False, "authority snapshot counters do not match historical ledger prefix", {
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
