"""Independent, runtime-free verification of portable Verigate proof packages."""
from __future__ import annotations
import base64, hashlib
from typing import Any
from attest.receipt import verify_execution_authorization, verify_execution_receipt
from core.evidence_manifest import verify_manifest
from core.proof_engine import canonical

def _nodes(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(n["type"], n["id"]): n for n in payload.get("nodes", [])}

def _node(payload: dict[str, Any], kind: str, node_id: str | None = None) -> dict[str, Any] | None:
    matches = [n for (t, i), n in _nodes(payload).items() if t == kind and (node_id is None or i == node_id)]
    return matches[0] if len(matches) == 1 else None

def _issuer_key(manifest: dict[str, Any]):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    raw = base64.b64decode(manifest["issuer_public_key_b64"], validate=True)
    return Ed25519PublicKey.from_public_bytes(raw)

def verify_authority_ledger(entries: list[dict[str, Any]]) -> tuple[bool, str, str]:
    previous = "0" * 64
    for expected_sequence, row in enumerate(entries, 1):
        if not isinstance(row, dict): return False, "authority ledger contains a malformed entry", previous
        if row.get("sequence") != expected_sequence: return False, "authority ledger sequence mismatch", previous
        if row.get("prev_event_hash") != previous: return False, "authority ledger chain mismatch", previous
        event = row.get("event")
        if not isinstance(event, dict): return False, "authority ledger event is malformed", previous
        actual = hashlib.sha256(canonical(event)).hexdigest()
        if actual != row.get("event_hash"): return False, "authority ledger event digest mismatch", previous
        previous = actual
    return True, "valid", previous

def _check_authority_binding(payload: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    auth_node = _node(payload, "execution_authorization"); ledger_node = _node(payload, "authority_ledger")
    historical = payload.get("historical_authority") or {}
    if auth_node is None: return False, "execution authorization evidence is missing", {}
    if ledger_node is None: return False, "authority ledger evidence is missing", {}
    auth = auth_node["data"]; auth_payload = auth.get("payload") if isinstance(auth, dict) else None
    ledger = ledger_node["data"]; entries = ledger.get("entries") if isinstance(ledger, dict) else None
    if not isinstance(auth_payload, dict) or not isinstance(entries, list): return False, "authority evidence is malformed", {}
    ok, reason, head = verify_authority_ledger(entries)
    if not ok: return False, reason, {"ledger_head": head}
    committed = auth_payload.get("authority_ledger_head_hash")
    if not isinstance(committed, str): return False, "execution authorization has no historical authority binding", {}
    if committed == "0" * 64:
        historical_entries = []
    else:
        historical_entries = []
        for row in entries:
            historical_entries.append(row)
            if row.get("event_hash") == committed:
                break
        if not historical_entries or historical_entries[-1].get("event_hash") != committed:
            return False, "historical authority ledger head mismatch", {"expected_head": committed, "actual_head": head}
    if historical.get("valid") is not True: return False, "historical authority proof is not valid", {"historical_reason": historical.get("reason")}
    details = historical.get("details")
    if isinstance(details, dict):
        if details.get("ledger_head_hash") not in (None, committed): return False, "historical authority detail head mismatch", {}
        if details.get("head_match") is False: return False, "historical authority head was reported as mismatched", {}
    return True, "historical authority binding verified", {
        "ledger_sequence": len(historical_entries),
        "live_ledger_sequence": len(entries),
        "ledger_head_hash": committed,
    }

def _check_authority_transition(payload: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    event_node = _node(payload, "authority_event")
    after_node = _node(payload, "authority_state_after")
    claim_node = _node(payload, "outcome_claim")
    ledger_node = _node(payload, "authority_ledger")
    if event_node is None or after_node is None:
        return False, "authority transition evidence is incomplete", {}
    if claim_node is None or ledger_node is None:
        return False, "authority transition is missing outcome or ledger evidence", {}
    event = event_node["data"]
    snapshot = after_node["data"]
    claim = claim_node["data"]
    entries = ledger_node["data"].get("entries")
    if not isinstance(event, dict) or not isinstance(snapshot, dict) or not isinstance(claim, dict):
        return False, "authority transition evidence is malformed", {}
    if event.get("evidence_ref") != claim.get("claim_id"):
        return False, "authority event is not bound to the outcome claim", {}
    if snapshot.get("source_event_id") != event.get("event_id"):
        return False, "post-learning authority snapshot is not bound to its event", {}
    if snapshot.get("agent_id") != event.get("agent_id") or snapshot.get("capability_id") != event.get("capability_id"):
        return False, "post-learning authority snapshot identity mismatch", {}
    if not isinstance(entries, list):
        return False, "authority ledger evidence is malformed", {}
    matching = [row for row in entries if row.get("event_id") == event.get("event_id")]
    if len(matching) != 1:
        return False, "authority transition event is absent from the ledger", {}
    if snapshot.get("ledger_head_hash") != matching[0].get("event_hash"):
        return False, "post-learning authority snapshot is not bound to ledger head", {}
    return True, "post-learning authority transition verified", {
        "event_id": event.get("event_id"),
        "claim_id": claim.get("claim_id"),
        "authority_snapshot_sha256": hashlib.sha256(canonical(snapshot)).hexdigest(),
        "ledger_head_hash": snapshot.get("ledger_head_hash"),
    }


def verify_proof(manifest: dict[str, Any], *, trusted_public_key_b64: str | None = None) -> dict[str, Any]:
    envelope = verify_manifest(manifest, trusted_public_key_b64); checks: dict[str, dict[str, Any]] = {}
    if not envelope["valid"]:
        return {"valid": False, "reason": envelope["reason"], "checks": {"manifest": {"valid": False, "reason": envelope["reason"]}}}
    payload = manifest["payload"]; checks["manifest"] = {"valid": True, "reason": "signed manifest, graph integrity, and Merkle root verified"}
    try: public_key = _issuer_key(manifest)
    except (ValueError, TypeError, base64.binascii.Error): return {"valid": False, "reason": "invalid embedded issuer public key", "checks": checks}
    auth_node = _node(payload, "execution_authorization")
    if auth_node is not None:
        ok, reason = verify_execution_authorization(auth_node["data"], public_key); checks["execution_authorization"] = {"valid": ok, "reason": reason}
        if not ok: return {"valid": False, "reason": reason, "checks": checks}
        receipt_node = _node(payload, "execution_receipt")
        if receipt_node is not None:
            ok, reason = verify_execution_receipt(receipt_node["data"], public_key, auth_node["data"]); checks["execution_receipt"] = {"valid": ok, "reason": reason}
            if not ok: return {"valid": False, "reason": reason, "checks": checks}
        ok, reason, details = _check_authority_binding(payload); checks["historical_authority"] = {"valid": ok, "reason": reason, "details": details}
        if not ok: return {"valid": False, "reason": reason, "checks": checks}
        if payload.get("proof_profile") == "authority_lifecycle":
            genesis_node = _node(payload, "genesis_authority")
            authority_node = _node(payload, "authority_state")
            if genesis_node is None or authority_node is None:
                return {"valid": False, "reason": "Genesis authority evidence is incomplete", "checks": checks}
            genesis = genesis_node["data"]
            authority_state = authority_node["data"]
            auth_payload = auth_node["data"]["payload"]
            if auth_payload.get("authority_state_sha256") != hashlib.sha256(canonical(authority_state)).hexdigest():
                return {"valid": False, "reason": "historical authority snapshot digest mismatch", "checks": checks}
            if genesis.get("authority_digest") and genesis.get("authority_digest") != auth_payload.get("authority_state_sha256"):
                return {"valid": False, "reason": "Genesis authority does not bind historical authority", "checks": checks}
            ok, reason, details = _check_authority_transition(payload)
            checks["authority_transition"] = {"valid": ok, "reason": reason, "details": details}
            if not ok: return {"valid": False, "reason": reason, "checks": checks}
    return {"valid": True, "reason": "valid portable Verigate proof", "proof_profile": payload.get("proof_profile", "integrity"), "root_digest": payload["root_digest"], "checks": checks, "node_count": len(payload.get("nodes", [])), "edge_count": len(payload.get("edges", []))}
