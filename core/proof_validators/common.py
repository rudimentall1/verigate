"""Shared graph and profile requirement helpers."""
from __future__ import annotations

from typing import Any
import hashlib
import json

from core.proof_profiles import profile_spec


def validate_requirements(
    payload: dict[str, Any], profile: str
) -> tuple[dict[str, Any] | None, set[str], list[dict[str, Any]], str | None]:
    spec = profile_spec(profile)
    if spec is None:
        return None, set(), [], f"unsupported proof profile: {profile}"

    node_types = {node["type"] for node in payload.get("nodes", [])}
    missing_nodes = sorted(spec["required_nodes"] - node_types)
    if missing_nodes:
        return spec, node_types, [], "proof profile missing required nodes: " + ", ".join(missing_nodes)

    edges = payload.get("edges", [])
    edge_pairs = {
        (edge["from"].split(":", 1)[0], edge["relation"], edge["to"].split(":", 1)[0])
        for edge in edges
    }
    missing_edges = sorted(spec["required_edges"] - edge_pairs)
    if missing_edges:
        return spec, node_types, edges, "proof profile missing required relations: " + ", ".join(
            f"{source}->{relation}->{target}" for source, relation, target in missing_edges
        )
    return spec, node_types, edges, None


def intent_context_digest(intent: dict[str, Any]) -> str:
    payload = {
        "purpose": intent.get("purpose", ""),
        "declared_context": intent.get("declared_context", {}),
        "input_provenance": intent.get("input_provenance", {}),
        "parent_intent_id": intent.get("parent_intent_id"),
        "requested_capability": intent.get("requested_capability"),
        "constraints": intent.get("constraints", {}),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def validate_context_binding(intent: dict[str, Any], decision: dict[str, Any]) -> tuple[bool, str]:
    expected = intent_context_digest(intent)
    actual = decision.get("context_sha256")
    if actual != expected:
        return False, "decision is not cryptographically bound to the canonical intent context"
    return True, "intent context binding is valid"


def validate_execution_enforcement_scope(
    execution_payload: dict[str, Any],
) -> tuple[bool, str]:
    """Validate only execution scopes that the proof protocol can independently establish.

    Genesis 2.0 currently proves the direct execution boundary. A transitive
    scope would require independent evidence that delegated child effects were
    themselves constrained; a signed claim inside the authorization is not
    sufficient evidence for an offline verifier.
    """
    graph = execution_payload.get("execution_graph")
    if not isinstance(graph, dict):
        return False, "execution authorization is missing execution graph binding"
    scope = graph.get("enforcement_scope", "direct") if graph else "direct"
    if scope == "direct":
        return True, "direct execution enforcement scope is valid"
    if scope == "transitive":
        return False, "transitive execution enforcement is not independently provable by authority-proof-v1"
    return False, f"unsupported execution enforcement scope: {scope}"


def validate_observed_effect_binding(
    claim_data: dict[str, Any],
    observed_effect: dict[str, Any],
    *,
    require_observation: bool = True,
) -> tuple[bool, str]:
    if not isinstance(observed_effect, dict) or not observed_effect:
        if require_observation:
            return False, "outcome claim requires a canonical observed-effect artifact"
        return True, "observed effect is optional for this claim"
    canonical_fields = {
        key: observed_effect.get(key)
        for key in (
            "verifier_type", "evidence_kind", "effect_status", "authorization_id",
            "action_sha256", "observed_at", "evidence_ref", "result_sha256", "observation",
        )
    }
    expected_observation_sha256 = hashlib.sha256(
        json.dumps(canonical_fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if observed_effect.get("observation_sha256") != expected_observation_sha256:
        return False, "observed effect fingerprint mismatch"
    if claim_data.get("authorization_id") != observed_effect.get("authorization_id"):
        return False, "observed effect is not bound to the outcome authorization"
    if claim_data.get("action_sha256") != observed_effect.get("action_sha256"):
        return False, "observed effect action fingerprint mismatch"
    if claim_data.get("evidence_kind") != observed_effect.get("evidence_kind"):
        return False, "observed effect evidence kind mismatch"
    if claim_data.get("evidence_ref") != observed_effect.get("evidence_ref"):
        return False, "observed effect evidence reference mismatch"
    if claim_data.get("result_sha256") != observed_effect.get("result_sha256"):
        return False, "observed effect result fingerprint mismatch"
    if claim_data.get("observed_effect") != observed_effect:
        return False, "outcome claim observed effect differs from canonical evidence"
    if claim_data.get("observed_effect_sha256") != hashlib.sha256(
        json.dumps(observed_effect, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest():
        return False, "outcome claim observed-effect fingerprint mismatch"
    return True, "observed effect is canonically bound to the outcome claim"


def validate_historical_authority_binding(
    snapshot: dict[str, Any],
    ledger_entries: list[dict[str, Any]],
    authority_policy: dict[str, Any],
    expected_head: str,
) -> tuple[bool, str]:
    """Recompute historical authority counters/state from the committed ledger prefix."""
    try:
        evaluated_at = float(snapshot["evaluated_at"])
        history_start_at = float(snapshot["history_start_at"])
        window_seconds = float(authority_policy["window_seconds"])
        probation_successes = int(authority_policy["probation_successes"])
        standard_successes = int(authority_policy["standard_successes"])
        limited_adverse_events = int(authority_policy["limited_adverse_events"])
        suspension_critical_events = int(authority_policy["suspension_critical_events"])
        multipliers = {
            "PROBATION": float(authority_policy["probation_multiplier"]),
            "LIMITED": float(authority_policy["limited_multiplier"]),
            "STANDARD": float(authority_policy["standard_multiplier"]),
            "ELEVATED": float(authority_policy["elevated_multiplier"]),
            "SUSPENDED": 0.0,
        }
    except (KeyError, TypeError, ValueError):
        return False, "historical authority policy or snapshot is malformed"
    if history_start_at != evaluated_at - window_seconds:
        return False, "historical authority history boundary is not policy-derived"
    policy_digest = hashlib.sha256(
        json.dumps(authority_policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if snapshot.get("authority_policy_sha256") != policy_digest:
        return False, "historical authority policy binding mismatch"
    committed = []
    if expected_head != "0" * 64:
        for row in ledger_entries:
            committed.append(row)
            if row.get("event_hash") == expected_head:
                break
        if not committed or committed[-1].get("event_hash") != expected_head:
            return False, "historical authority ledger head is not present"
    for row in ledger_entries[len(committed):]:
        event = row.get("event") if isinstance(row, dict) else None
        if not isinstance(event, dict):
            return False, "historical authority ledger contains malformed future event"
        occurred_at = event.get("occurred_at")
        if not isinstance(occurred_at, (int, float)) or isinstance(occurred_at, bool):
            return False, "historical authority future event timestamp is invalid"
        if float(occurred_at) <= evaluated_at:
            return False, "historical authority head is inconsistent with the evaluation time"

    successes = adverse = critical = 0
    adverse_types = {"EXECUTION_FAILED", "AUTHORIZATION_REJECTED", "POLICY_VIOLATION", "TAMPER_DETECTED"}
    critical_types = {"TAMPER_DETECTED", "POLICY_VIOLATION"}
    for row in committed:
        event = row.get("event") if isinstance(row, dict) else None
        if not isinstance(event, dict):
            return False, "historical authority ledger contains malformed event"
        occurred_at = event.get("occurred_at")
        if not isinstance(occurred_at, (int, float)) or isinstance(occurred_at, bool):
            return False, "historical authority event timestamp is invalid"
        if history_start_at <= float(occurred_at) <= evaluated_at:
            if event.get("event_type") == "EXECUTION_CONFIRMED":
                successes += 1
            if event.get("event_type") in adverse_types:
                adverse += 1
            if event.get("event_type") in critical_types:
                critical += 1
    if (snapshot.get("successes"), snapshot.get("adverse_events"), snapshot.get("critical_events")) != (successes, adverse, critical):
        return False, "historical authority counters do not match the committed ledger window"
    if critical >= suspension_critical_events:
        expected_state = "SUSPENDED"
        expected_reason = "critical authority event observed"
    elif adverse >= limited_adverse_events:
        expected_state = "LIMITED"
        expected_reason = "adverse outcome threshold reached"
    elif successes >= standard_successes and adverse <= 1:
        expected_state = "ELEVATED"
        expected_reason = "verified success threshold reached with bounded adverse history"
    elif successes >= probation_successes and adverse <= 1:
        expected_state = "STANDARD"
        expected_reason = "probation success threshold reached"
    else:
        expected_state = "PROBATION"
        expected_reason = "insufficient verified history for broader authority"
    if snapshot.get("state") != expected_state:
        return False, "historical authority state is not deterministically justified by the ledger and policy"
    if snapshot.get("multiplier") != multipliers[expected_state]:
        return False, "historical authority multiplier is inconsistent with the authority policy"
    if snapshot.get("reason") != expected_reason:
        return False, "historical authority reason is inconsistent with the authority policy"
    return True, "historical authority snapshot is deterministically bound"


def validate_authority_learning_binding(
    claim_data: dict[str, Any],
    attestation_payload: dict[str, Any],
    event_data: dict[str, Any],
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
    ledger_entries: list[dict[str, Any]],
    authority_policy: dict[str, Any],
    expected_before_head: str,
) -> tuple[bool, str]:
    """Prove that learning and post-learning authority are deterministic from evidence.

    The event and post-learning snapshot are not trusted merely because their
    hashes/signature are intact. Their semantic content must follow the signed
    outcome, the historical ledger, and the authority policy.
    """
    if claim_data.get("status") == "SUCCEEDED":
        expected_event_type = "EXECUTION_CONFIRMED"
    elif claim_data.get("status") == "FAILED":
        expected_event_type = "EXECUTION_FAILED"
    else:
        return False, "authority lifecycle learning requires a terminal independent outcome"

    agent_id = claim_data.get("agent_id")
    capability_id = before_snapshot.get("capability_id")
    identity_id = before_snapshot.get("identity_id")
    claim_id = claim_data.get("claim_id")
    if event_data.get("agent_id") != agent_id or event_data.get("capability_id") != capability_id:
        return False, "authority event identity binding is inconsistent"
    if identity_id is not None and event_data.get("identity_id") != identity_id:
        return False, "authority event identity_id is inconsistent with historical authority"
    if event_data.get("event_type") != expected_event_type:
        return False, "authority event type is inconsistent with the canonical outcome"
    if event_data.get("evidence_ref") != claim_id:
        return False, "authority event is not bound to the canonical outcome claim"
    expected_event_id = hashlib.sha256(
        f"{agent_id}:{capability_id}:{expected_event_type}:{claim_id}".encode("utf-8")
    ).hexdigest()
    if event_data.get("event_id") != expected_event_id:
        return False, "authority event id is not deterministic from the canonical learning event"

    metadata = event_data.get("metadata") if isinstance(event_data.get("metadata"), dict) else {}
    if "outcome_attestation_id" in metadata:
        if metadata.get("outcome_attestation_id") != attestation_payload.get("attestation_id"):
            return False, "authority event is not bound to the outcome attestation"
    if "attestation_type" in metadata:
        if metadata.get("attestation_type") != attestation_payload.get("attestor_type"):
            return False, "authority event attestation type is inconsistent"

    try:
        evaluated_at = float(after_snapshot["evaluated_at"])
        history_start_at = float(after_snapshot["history_start_at"])
        window_seconds = float(authority_policy["window_seconds"])
        probation_successes = int(authority_policy["probation_successes"])
        standard_successes = int(authority_policy["standard_successes"])
        limited_adverse_events = int(authority_policy["limited_adverse_events"])
        suspension_critical_events = int(authority_policy["suspension_critical_events"])
        multipliers = {
            "PROBATION": float(authority_policy["probation_multiplier"]),
            "LIMITED": float(authority_policy["limited_multiplier"]),
            "STANDARD": float(authority_policy["standard_multiplier"]),
            "ELEVATED": float(authority_policy["elevated_multiplier"]),
            "SUSPENDED": 0.0,
        }
    except (KeyError, TypeError, ValueError):
        return False, "authority policy or post-learning timestamp is malformed"
    if history_start_at != evaluated_at - window_seconds:
        return False, "post-learning authority history boundary is not derivable from the authority policy"
    if after_snapshot.get("authority_policy_sha256") != hashlib.sha256(
        json.dumps(authority_policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest():
        return False, "post-learning authority policy binding mismatch"
    if after_snapshot.get("agent_id") != agent_id or after_snapshot.get("capability_id") != capability_id:
        return False, "post-learning authority snapshot identity mismatch"

    canonical_event_hash = hashlib.sha256(
        json.dumps(event_data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    matching = [
        row for row in ledger_entries
        if isinstance(row, dict) and row.get("event_id") == event_data.get("event_id")
    ]
    if len(matching) != 1:
        return False, "authority transition event is absent or duplicated in the authority ledger"
    if matching[0].get("event_hash") != canonical_event_hash or matching[0].get("event") != event_data:
        return False, "authority ledger event is not an exact copy of the canonical authority event"
    if after_snapshot.get("ledger_head_hash") != canonical_event_hash:
        return False, "post-learning authority snapshot is not bound to the learning event hash"
    try:
        event_occurred_at = float(event_data["occurred_at"])
        before_evaluated_at = float(before_snapshot["evaluated_at"])
    except (KeyError, TypeError, ValueError):
        return False, "authority learning timestamps are malformed"
    if event_occurred_at > evaluated_at or event_occurred_at < history_start_at:
        return False, "learning event is outside the post-learning authority evaluation window"
    if before_evaluated_at > evaluated_at:
        return False, "post-learning authority is evaluated before the historical authority snapshot"
    if before_snapshot.get("ledger_head_hash") != expected_before_head:
        return False, "historical authority snapshot is not bound to the authorization ledger head"
    for row in ledger_entries:
        if row.get("event_hash") == expected_before_head:
            prior_sequence = row.get("sequence")
            break
    else:
        prior_sequence = 0
    if expected_before_head != "0" * 64 and prior_sequence == 0:
        return False, "authorization ledger head is not present in the authority ledger"
    event_sequence = matching[0].get("sequence")
    if not isinstance(event_sequence, int) or event_sequence <= prior_sequence:
        return False, "learning event does not extend the historical authorization ledger head"
    for row in ledger_entries:
        if isinstance(row, dict) and isinstance(row.get("sequence"), int) and row["sequence"] > event_sequence:
            future_event = row.get("event")
            if isinstance(future_event, dict) and float(future_event.get("occurred_at", evaluated_at + 1)) <= evaluated_at:
                return False, "post-learning snapshot is not bound to the ledger head at its evaluation time"

    successes = adverse = critical = 0
    adverse_types = {"EXECUTION_FAILED", "AUTHORIZATION_REJECTED", "POLICY_VIOLATION", "TAMPER_DETECTED"}
    critical_types = {"TAMPER_DETECTED", "POLICY_VIOLATION"}
    for row in ledger_entries:
        event = row.get("event") if isinstance(row, dict) else None
        if not isinstance(event, dict):
            return False, "authority ledger contains malformed learning evidence"
        occurred_at = event.get("occurred_at")
        if not isinstance(occurred_at, (int, float)) or isinstance(occurred_at, bool):
            return False, "authority event has an invalid occurrence timestamp"
        if history_start_at <= float(occurred_at) <= evaluated_at:
            if event.get("event_type") == "EXECUTION_CONFIRMED":
                successes += 1
            if event.get("event_type") in adverse_types:
                adverse += 1
            if event.get("event_type") in critical_types:
                critical += 1

    if (after_snapshot.get("successes"), after_snapshot.get("adverse_events"), after_snapshot.get("critical_events")) != (successes, adverse, critical):
        return False, "post-learning authority counters do not match the historical ledger window"

    previous_state = before_snapshot.get("state")
    if previous_state == "SUSPENDED":
        expected_state = "SUSPENDED"
        expected_reason = "suspended until an explicit authority reset"
    elif critical >= suspension_critical_events:
        expected_state = "SUSPENDED"
        expected_reason = "critical authority event observed"
    elif adverse >= limited_adverse_events:
        expected_state = "LIMITED"
        expected_reason = "adverse outcome threshold reached"
    elif successes >= standard_successes and adverse <= 1:
        expected_state = "ELEVATED"
        expected_reason = "verified success threshold reached with bounded adverse history"
    elif successes >= probation_successes and adverse <= 1:
        expected_state = "STANDARD"
        expected_reason = "probation success threshold reached"
    else:
        expected_state = "PROBATION"
        expected_reason = "insufficient verified history for broader authority"

    if after_snapshot.get("state") != expected_state:
        return False, "post-learning authority state is not deterministically justified by the ledger and policy"
    if after_snapshot.get("multiplier") != multipliers[expected_state]:
        return False, "post-learning authority multiplier is inconsistent with the authority policy"
    if after_snapshot.get("reason") != expected_reason:
        return False, "post-learning authority reason is inconsistent with the authority policy"
    return True, "learning event and post-learning authority are deterministically bound"


def validate_external_state_execution_scope(
    execution_payload: dict[str, Any],
    execution_receipt_payload: dict[str, Any],
) -> tuple[bool, str]:
    """Validate the execution contract recorded for policy-required external state.

    The proof verifies the signed adapter contract and exact state binding. It
    does not claim to sandbox arbitrary generic adapter internals; "atomic"
    remains an explicit trusted-adapter boundary. EVM adapters additionally
    enforce the committed guard on-chain.
    """
    required = bool(execution_payload.get("external_state_required"))
    scope = execution_receipt_payload.get("execution_external_state_scope")
    external_state = execution_payload.get("external_state")
    requirement = execution_payload.get("external_state_requirement")

    if not required:
        if scope not in (None, "atomic"):
            return False, f"unsupported execution external-state scope: {scope}"
        return True, "external state execution is not required"

    if scope != "atomic":
        return False, "required external state execution is not atomically enforced"
    if not isinstance(external_state, dict) or not external_state:
        return False, "required external state binding is missing"
    if not isinstance(requirement, dict):
        return False, "required external state policy requirement is missing"

    state_json = json.dumps(
        external_state, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    requirement_json = json.dumps(
        requirement, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    if execution_payload.get("external_state_sha256") != hashlib.sha256(state_json).hexdigest():
        return False, "external state fingerprint mismatch"
    if execution_payload.get("external_state_requirement_sha256") != hashlib.sha256(requirement_json).hexdigest():
        return False, "external state requirement fingerprint mismatch"
    if external_state.get("kind") != requirement.get("kind"):
        return False, "external state kind does not satisfy policy requirement"
    reference = external_state.get("reference")
    if not isinstance(reference, str) or not reference.strip():
        return False, "external state binding is missing reference"
    digest_value = external_state.get("digest")
    if not isinstance(digest_value, str) or len(digest_value) != 64:
        return False, "external state binding has invalid digest"
    try:
        int(digest_value, 16)
    except ValueError:
        return False, "external state binding digest is not hexadecimal"
    return True, "required external state execution is atomically bound"
