"""Independent historical verification of Verigate authority decisions."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from attest.receipt import verify_execution_authorization


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
    actual_head = rows[-1]["event_hash"] if rows else "0" * 64
    if actual_head != expected_head:
        return False, "historical authority ledger head mismatch", {
            "ledger_valid": True, "expected_head": expected_head, "actual_head": actual_head,
        }
    auth_valid, auth_reason = verify_execution_authorization(authorization, public_key)
    if not auth_valid:
        return False, auth_reason, {"ledger_valid": True, "head_match": True}
    return True, "historical authority decision verified", {
        "ledger_valid": True, "head_match": True, "ledger_sequence": len(rows),
        "authority_state": payload.get("authority_state"),
        "authority_multiplier": payload.get("authority_multiplier"),
        "ledger_head_hash": actual_head,
    }
