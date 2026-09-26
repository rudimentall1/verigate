"""Machine-verifiable assertions for the Verigate authority proof protocol."""
from __future__ import annotations

import hashlib
from typing import Any

from core.proof_engine import canonical, digest

PROOF_PROTOCOL = "verigate-authority-proof-v1"


def _nodes(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {(n["type"], n["id"]): n for n in payload.get("nodes", [])}


def _has_edge(payload: dict[str, Any], source: str, relation: str, target: str) -> bool:
    return any(e.get("from") == source and e.get("relation") == relation and e.get("to") == target for e in payload.get("edges", []))


def _node(nodes: dict[tuple[str, str], dict[str, Any]], kind: str) -> dict[str, Any] | None:
    matches = [n for (t, _), n in nodes.items() if t == kind]
    return matches[0] if len(matches) == 1 else None


def _assertion(assertion_id: str, kind: str, subject: str, predicate: str, object_ref: str, evidence: list[str]) -> dict[str, Any]:
    body = {"id": assertion_id, "kind": kind, "subject": subject, "predicate": predicate, "object": object_ref, "evidence": evidence}
    body["sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    return body


def build_authority_assertions(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive the protocol's semantic assertions from signed manifest evidence."""
    payload = manifest["payload"]
    nodes = _nodes(payload)
    identity = _node(nodes, "identity")
    capability = _node(nodes, "capability")
    intent = _node(nodes, "action_intent")
    authority = _node(nodes, "authority_state")
    genesis = _node(nodes, "genesis_authority")
    decision = _node(nodes, "decision")
    authorization = _node(nodes, "execution_authorization")
    receipt = _node(nodes, "execution_receipt")
    claim = _node(nodes, "outcome_claim")
    attestation = _node(nodes, "outcome_attestation")
    event = _node(nodes, "authority_event")
    after = _node(nodes, "authority_state_after")
    ledger = _node(nodes, "authority_ledger")
    required = {"identity": identity, "capability": capability, "action_intent": intent, "authority_state": authority, "genesis_authority": genesis, "decision": decision, "execution_authorization": authorization, "execution_receipt": receipt, "outcome_claim": claim, "outcome_attestation": attestation, "authority_event": event, "authority_state_after": after, "authority_ledger": ledger}
    if any(v is None for v in required.values()):
        raise ValueError("authority proof protocol requires complete lifecycle evidence")
    refs = {k: f"{v['type']}:{v['id']}" for k, v in required.items()}
    ap = authorization["data"].get("payload", {})
    rp = receipt["data"].get("payload", {})
    cp = claim["data"]
    ep = event["data"]
    sp = after["data"]
    entries = ledger["data"].get("entries", [])
    matching = [row for row in entries if row.get("event_id") == ep.get("event_id")]
    assertions = [
        _assertion("A1", "identity", refs["identity"], "possessed_capability", refs["capability"], [refs["identity"], refs["capability"]]),
        _assertion("A2", "intent", refs["action_intent"], "proposed_by", identity["data"].get("agent_id", payload.get("agent_id")), [refs["action_intent"], refs["identity"]]),
        _assertion("A3", "authority", refs["authority_state"], "permitted", refs["action_intent"], [refs["authority_state"], refs["action_intent"], refs["capability"]]),
        _assertion("A4", "authorization", refs["execution_authorization"], "derived_from", refs["authority_state"], [refs["decision"], refs["execution_authorization"], refs["authority_state"], refs["genesis_authority"]]),
        _assertion("A5", "execution", refs["execution_receipt"], "consumed_authorization", refs["execution_authorization"], [refs["execution_authorization"], refs["execution_receipt"]]),
        _assertion("A6", "observation", refs["outcome_claim"], "observes", refs["execution_receipt"], [refs["execution_receipt"], refs["outcome_claim"], refs["outcome_attestation"]]),
        _assertion("A7", "learning", refs["authority_event"], "justified_by", refs["outcome_claim"], [refs["outcome_claim"], refs["authority_event"]]),
        _assertion("A8", "learning", refs["authority_state_after"], "produced_by", refs["authority_event"], [refs["authority_event"], refs["authority_state_after"]]),
        _assertion("A9", "integrity", refs["authority_state_after"], "ledger_bound", refs["authority_ledger"], [refs["authority_state_after"], refs["authority_ledger"]]),
    ]
    # Keep the derived assertions strict: this is a protocol, not a label set.
    checks = [
        _has_edge(payload, refs["identity"], "AUTHENTICATES", refs["action_intent"]),
        _has_edge(payload, refs["capability"], "AUTHORIZES", refs["action_intent"]),
        ap.get("authority_state_sha256") == hashlib.sha256(canonical(authority["data"])).hexdigest(),
        _has_edge(payload, refs["decision"], "MINTS", refs["execution_authorization"]),
        _has_edge(payload, refs["execution_authorization"], "PRODUCES", refs["execution_receipt"]),
        rp.get("authorization_id") == ap.get("authorization_id"),
        _has_edge(payload, refs["execution_receipt"], "OBSERVED_BY", refs["outcome_claim"]),
        _has_edge(payload, refs["outcome_attestation"], "ATTESTS", refs["outcome_claim"]),
        _has_edge(payload, refs["outcome_claim"], "INFORMS", refs["authority_event"]),
        _has_edge(payload, refs["authority_event"], "TRANSITIONS_TO", refs["authority_state_after"]),
        ep.get("evidence_ref") == cp.get("claim_id"),
        sp.get("source_event_id") == ep.get("event_id"),
        len(matching) == 1 and sp.get("ledger_head_hash") == matching[0].get("event_hash"),
    ]
    if not all(checks):
        raise ValueError("authority proof protocol assertion preconditions failed")
    return assertions


def assertion_set_digest(assertions: list[dict[str, Any]]) -> str:
    return digest(assertions)


def verify_authority_assertions(manifest: dict[str, Any], assertions: Any = None) -> tuple[bool, str, dict[str, Any]]:
    if manifest.get("payload", {}).get("proof_profile") != "authority_lifecycle":
        return True, "assertion protocol not required for this profile", {}
    if assertions is None:
        assertions = manifest.get("payload", {}).get("authority_assertions")
    if not isinstance(assertions, list):
        return False, "authority proof assertions are missing", {}
    try:
        expected = build_authority_assertions(manifest)
    except (KeyError, TypeError, ValueError) as exc:
        return False, str(exc), {}
    if assertions != expected:
        return False, "authority proof assertions do not match signed evidence", {}
    return True, "authority proof assertions verified", {"protocol": PROOF_PROTOCOL, "assertion_count": len(assertions), "assertion_set_sha256": assertion_set_digest(assertions)}
