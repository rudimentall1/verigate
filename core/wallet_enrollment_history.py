"""Historical verification of governed Anna installation wallet enrollments."""
from __future__ import annotations

import base64
import hashlib
import math
import re
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.governance import GovernancePolicy, verify_governance_quorum
from core.proof_engine import digest


_EVM_ADDRESS = re.compile(r"^0x[0-9a-f]{40}$")


def _finite_timestamp(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _enrollment_fields_match(action: dict[str, Any], current: dict[str, Any]) -> bool:
    public_key_b64 = action.get("issuer_public_key_b64")
    try:
        raw_key = base64.b64decode(public_key_b64, validate=True)
        if len(raw_key) != 32:
            return False
        Ed25519PublicKey.from_public_bytes(raw_key)
    except (TypeError, ValueError):
        return False

    key_id = hashlib.sha256(raw_key).hexdigest()
    principal = "anna-installation:" + key_id
    chain_id = action.get("chain_id")
    network = action.get("network")
    wallet_address = action.get("wallet_address")
    min_confirmations = action.get("min_confirmations")
    if (
        action.get("installation_principal") != principal
        or action.get("issuer_key_id") != key_id
        or not isinstance(chain_id, int)
        or isinstance(chain_id, bool)
        or chain_id <= 0
        or not isinstance(network, str)
        or not network
        or network != network.strip().lower()
        or not isinstance(wallet_address, str)
        or not _EVM_ADDRESS.fullmatch(wallet_address)
        or not isinstance(min_confirmations, int)
        or isinstance(min_confirmations, bool)
        or min_confirmations < 1
    ):
        return False

    expected = {
        "enrollment_id": action.get("enrollment_id"),
        "installation_principal": principal,
        "issuer_key_id": key_id,
        "issuer_public_key_b64": public_key_b64,
        "chain_id": chain_id,
        "network": network,
        "wallet_address": wallet_address,
        "min_confirmations": min_confirmations,
    }
    return all(current.get(field) == value for field, value in expected.items())


def resolve_historical_wallet_enrollment(
    governance_history: list[dict[str, Any]],
    enrollment_snapshot: dict[str, Any],
    attested_at: float,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Resolve the wallet enrollment state at a signed outcome's attested_at.

    Stored governance envelopes, rather than the mutable registry status, are
    the source for historical state. The final registry row is still checked
    against the replayed state so deleting or altering an action is detected.
    """
    if not _finite_timestamp(attested_at):
        return False, "wallet enrollment attestation timestamp is invalid", None
    if not isinstance(enrollment_snapshot, dict):
        return False, "wallet enrollment registry snapshot is malformed", None

    enrollment_id = enrollment_snapshot.get("enrollment_id")
    principal = enrollment_snapshot.get("installation_principal")
    if not isinstance(enrollment_id, str) or not enrollment_id:
        return False, "wallet enrollment identity is missing", None
    if not isinstance(principal, str) or not principal:
        return False, "wallet enrollment installation principal is missing", None
    if not isinstance(governance_history, list) or not governance_history:
        return False, "wallet enrollment governance history is empty", None

    relevant: list[tuple[float, dict[str, Any]]] = []
    seen_action_ids: set[str] = set()
    for envelope in governance_history:
        if not isinstance(envelope, dict):
            return False, "wallet enrollment governance envelope is malformed", None
        action = envelope.get("action")
        if not isinstance(action, dict):
            return False, "wallet enrollment governance action is malformed", None

        action_id = action.get("action_id")
        action_enrollment_id = action.get("enrollment_id")
        if (
            not isinstance(action_id, str)
            or not action_id
            or action_id in seen_action_ids
            or not isinstance(action_enrollment_id, str)
            or not action_enrollment_id
        ):
            return False, "wallet enrollment governance action identity is missing or duplicated", None
        seen_action_ids.add(action_id)
        if action_enrollment_id != enrollment_id:
            continue

        if action.get("action") not in {"WALLET_ENROLL", "WALLET_REVOKE"}:
            return False, "unsupported wallet enrollment governance transition", None
        approvals = envelope.get("approvals")
        policy_data = envelope.get("governance_policy")
        if not isinstance(approvals, list) or not approvals:
            return False, "wallet enrollment governance action has no approval evidence", None
        if not isinstance(policy_data, dict):
            return False, "wallet enrollment governance policy evidence is missing", None
        if envelope.get("algorithm") != "Ed25519-MULTIPARTY":
            return False, "unsupported wallet enrollment governance algorithm", None

        action_issued_at = action.get("issued_at")
        if not _finite_timestamp(action_issued_at):
            return False, "wallet enrollment governance action timestamp is invalid", None

        approval_ids: set[str] = set()
        approval_issue_times: list[float] = []
        for approval in approvals:
            approval_payload = approval.get("payload") if isinstance(approval, dict) else None
            approval_id = approval_payload.get("approval_id") if isinstance(approval_payload, dict) else None
            issued_at = approval_payload.get("issued_at") if isinstance(approval_payload, dict) else None
            if (
                not isinstance(approval_id, str)
                or not approval_id
                or approval_id in approval_ids
            ):
                return False, "wallet enrollment approval identity is missing or duplicated", None
            if not _finite_timestamp(issued_at):
                return False, "wallet enrollment approval timestamp is invalid", None
            approval_ids.add(approval_id)
            approval_issue_times.append(float(issued_at))

        verification_time = max([float(action_issued_at), *approval_issue_times])
        try:
            policy = GovernancePolicy.from_dict(policy_data)
            if (
                policy.digest != action.get("governance_policy_sha256")
                or envelope.get("governance_policy_sha256") != policy.digest
                or envelope.get("action_sha256") != digest(action)
            ):
                return False, "wallet enrollment governance evidence fingerprint mismatch", None
            valid_quorum, quorum_reason = verify_governance_quorum(
                action, approvals, policy, now=verification_time,
            )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            return False, f"invalid wallet enrollment governance quorum evidence: {exc}", None
        if not valid_quorum:
            return False, f"wallet enrollment governance quorum verification failed: {quorum_reason}", None
        relevant.append((verification_time, action))

    if not relevant:
        return False, "wallet enrollment governance history has no enrollment action", None

    relevant.sort(key=lambda item: item[0])
    previous_time: float | None = None
    final_status = "UNREGISTERED"
    historical_state: dict[str, Any] | None = None
    replayed_enrollment: dict[str, Any] | None = None
    for effective_at, action in relevant:
        if previous_time is not None and effective_at <= previous_time:
            return False, "wallet enrollment governance actions have ambiguous or non-monotonic ordering", None
        previous_time = effective_at
        operation = action["action"]

        if operation == "WALLET_ENROLL":
            if final_status != "UNREGISTERED":
                return False, "wallet enrollment governance history contains duplicate enrollment", None
            if not _enrollment_fields_match(action, enrollment_snapshot):
                return False, "wallet enrollment action does not match registry snapshot", None
            replayed_enrollment = {
                field: action[field]
                for field in (
                    "enrollment_id", "installation_principal", "issuer_key_id",
                    "issuer_public_key_b64", "chain_id", "network",
                    "wallet_address", "min_confirmations",
                )
            }
            final_status = "ACTIVE"
        else:
            if final_status != "ACTIVE":
                return False, "wallet enrollment revocation does not follow active enrollment", None
            final_status = "REVOKED"

        if effective_at <= float(attested_at):
            historical_state = dict(replayed_enrollment or {})
            historical_state["status"] = final_status
            historical_state["revoked_at"] = None

    if replayed_enrollment is None:
        return False, "wallet enrollment governance history has no valid enrollment", None

    for field, expected in replayed_enrollment.items():
        if enrollment_snapshot.get(field) != expected:
            return False, "wallet enrollment registry snapshot does not match governance replay", None
    if enrollment_snapshot.get("status") != final_status:
        return False, "wallet enrollment registry status does not match governance replay", None

    revoked_at = enrollment_snapshot.get("revoked_at")
    if final_status == "REVOKED":
        if not _finite_timestamp(revoked_at) or float(revoked_at) <= 0:
            return False, "revoked wallet enrollment has an invalid revocation timestamp", None
    elif revoked_at is not None:
        return False, "active wallet enrollment has a revocation timestamp", None

    created_at = enrollment_snapshot.get("created_at")
    if not _finite_timestamp(created_at) or float(created_at) <= 0:
        return False, "wallet enrollment creation timestamp is invalid", None

    if historical_state is None:
        historical_state = dict(replayed_enrollment)
        historical_state["status"] = "UNREGISTERED"
        historical_state["revoked_at"] = None

    historical_enrollment = dict(enrollment_snapshot)
    historical_enrollment.update(historical_state)
    return True, "wallet enrollment governance state resolved at attestation time", historical_enrollment
