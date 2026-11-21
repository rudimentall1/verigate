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


def resolve_portable_wallet_enrollment_history(
    history_data: dict[str, Any],
    enrollment_snapshots: list[dict[str, Any]],
    *,
    installation_principal: str,
    chain_id: int,
    wallet_address: str,
    attested_at: float,
    trusted_policy_digests: list[str] | set[str] | tuple[str, ...] | None = None,
    trusted_history_digests: list[str] | set[str] | tuple[str, ...] | None = None,
) -> tuple[bool, str, dict[str, Any] | None, dict[str, Any]]:
    """Verify the complete portable wallet history and resolve its historical active row.

    Policy and history digests are optional for compatibility. When supplied,
    they are independent allowlists and must match every policy and the exact
    canonical complete-history root carried by the proof.
    """
    checks: dict[str, Any] = {}

    def failure(reason: str):
        return False, reason, None, checks

    if (
        not isinstance(history_data, dict)
        or history_data.get("installation_principal") != installation_principal
        or not isinstance(installation_principal, str)
        or not installation_principal.startswith("anna-installation:")
        or isinstance(chain_id, bool)
        or not isinstance(chain_id, int)
        or chain_id <= 0
        or not isinstance(wallet_address, str)
        or not re.fullmatch(r"0x[0-9a-fA-F]{40}", wallet_address)
        or isinstance(attested_at, bool)
        or not isinstance(attested_at, (int, float))
        or not math.isfinite(float(attested_at))
    ):
        return failure("portable wallet enrollment verification request is malformed")

    envelopes = history_data.get("envelopes")
    if not isinstance(envelopes, list) or not envelopes:
        return failure("wallet enrollment governance history is empty")
    try:
        ordered_history = sorted(
            envelopes,
            key=lambda item: item.get("action", {}).get("action_id", "")
            if isinstance(item, dict) else "",
        )
    except (AttributeError, TypeError):
        return failure("wallet enrollment governance history is malformed")
    history_sha256 = digest(ordered_history)
    if history_data.get("history_sha256") != history_sha256:
        checks["wallet_enrollment_history_anchor"] = {
            "valid": False,
            "pinned": trusted_history_digests is not None,
            "history_sha256": history_data.get("history_sha256"),
            "reason": "wallet enrollment governance history fingerprint mismatch",
        }
        return failure("wallet enrollment governance history fingerprint mismatch")

    def normalize(values: Any, label: str) -> set[str] | None:
        if values is None:
            return None
        if isinstance(values, str):
            values = [values]
        if not isinstance(values, (list, tuple, set)) or not values:
            raise ValueError(f"at least one trusted {label} digest is required")
        result = set()
        for value in values:
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(char not in "0123456789abcdefABCDEF" for char in value)
            ):
                raise ValueError(f"trusted {label} digest must be 64 hexadecimal characters")
            result.add(value.lower())
        return result

    try:
        trusted_history = normalize(trusted_history_digests, "wallet enrollment history")
        trusted_policies = normalize(trusted_policy_digests, "wallet governance policy")
    except ValueError as exc:
        return failure(str(exc))

    if trusted_history is None:
        checks["wallet_enrollment_history_anchor"] = {
            "valid": True,
            "pinned": False,
            "history_sha256": history_sha256,
            "trusted_history_sha256": [],
            "reason": "no independent wallet enrollment history digest supplied",
        }
    else:
        untrusted_history = sorted({history_sha256} - trusted_history)
        checks["wallet_enrollment_history_anchor"] = {
            "valid": not untrusted_history,
            "pinned": True,
            "history_sha256": history_sha256,
            "trusted_history_sha256": sorted(trusted_history),
            "untrusted_history_sha256": untrusted_history,
            "reason": (
                "wallet enrollment history matches trusted digest"
                if not untrusted_history
                else "wallet enrollment history digest is not present in the trusted allowlist"
            ),
        }
        if untrusted_history:
            return failure(checks["wallet_enrollment_history_anchor"]["reason"])

    if not isinstance(enrollment_snapshots, list) or not enrollment_snapshots:
        return failure("wallet enrollment registry snapshots are missing")
    snapshot_by_id: dict[str, dict[str, Any]] = {}
    for snapshot in enrollment_snapshots:
        if not isinstance(snapshot, dict):
            return failure("wallet enrollment registry snapshot is malformed")
        enrollment_id = snapshot.get("enrollment_id")
        if (
            not isinstance(enrollment_id, str)
            or not enrollment_id
            or enrollment_id in snapshot_by_id
            or snapshot.get("installation_principal") != installation_principal
        ):
            return failure("wallet enrollment registry identity is missing, duplicated or mismatched")
        snapshot_by_id[enrollment_id] = snapshot

    seen_action_ids: set[str] = set()
    policy_digests: set[str] = set()
    for envelope in ordered_history:
        if not isinstance(envelope, dict):
            return failure("wallet enrollment governance envelope is malformed")
        action = envelope.get("action")
        approvals = envelope.get("approvals")
        policy_data = envelope.get("governance_policy")
        if not isinstance(action, dict) or not isinstance(policy_data, dict):
            return failure("wallet enrollment governance envelope is incomplete")
        action_id = action.get("action_id")
        enrollment_id = action.get("enrollment_id")
        if (
            not isinstance(action_id, str)
            or not action_id
            or action_id in seen_action_ids
            or enrollment_id not in snapshot_by_id
        ):
            return failure("wallet enrollment governance action identity is duplicated or targets a missing row")
        seen_action_ids.add(action_id)
        if (
            action.get("action") not in {"WALLET_ENROLL", "WALLET_REVOKE"}
            or not isinstance(approvals, list)
            or not approvals
            or envelope.get("algorithm") != "Ed25519-MULTIPARTY"
        ):
            return failure("wallet enrollment governance action or approval evidence is invalid")

        action_issued_at = action.get("issued_at")
        if (
            isinstance(action_issued_at, bool)
            or not isinstance(action_issued_at, (int, float))
            or not math.isfinite(float(action_issued_at))
        ):
            return failure("wallet enrollment governance action timestamp is invalid")
        approval_ids: set[str] = set()
        approval_issued_at: list[float] = []
        for approval in approvals:
            approval_payload = approval.get("payload") if isinstance(approval, dict) else None
            approval_id = (
                approval_payload.get("approval_id")
                if isinstance(approval_payload, dict) else None
            )
            issued_at = (
                approval_payload.get("issued_at")
                if isinstance(approval_payload, dict) else None
            )
            if (
                not isinstance(approval_id, str)
                or not approval_id
                or approval_id in approval_ids
                or isinstance(issued_at, bool)
                or not isinstance(issued_at, (int, float))
                or not math.isfinite(float(issued_at))
            ):
                return failure("wallet enrollment governance approval identity or timestamp is invalid")
            approval_ids.add(approval_id)
            approval_issued_at.append(float(issued_at))

        verification_time = max([float(action_issued_at), *approval_issued_at])
        try:
            policy = GovernancePolicy.from_dict(policy_data)
            if (
                policy.digest != action.get("governance_policy_sha256")
                or envelope.get("governance_policy_sha256") != policy.digest
                or envelope.get("action_sha256") != digest(action)
            ):
                return failure("wallet enrollment governance evidence fingerprint mismatch")
            valid_quorum, quorum_reason = verify_governance_quorum(
                action, approvals, policy, now=verification_time,
            )
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            return failure(f"invalid wallet enrollment governance quorum evidence: {exc}")
        if not valid_quorum:
            return failure(f"wallet enrollment governance quorum verification failed: {quorum_reason}")
        policy_digests.add(policy.digest)

    ordered_policy_digests = sorted(policy_digests)
    if trusted_policies is None:
        checks["wallet_governance_policy_trust_anchor"] = {
            "valid": True,
            "pinned": False,
            "policy_sha256": ordered_policy_digests,
            "trusted_policy_sha256": [],
            "reason": "wallet governance quorum is verified, but the governor roster is not externally pinned",
        }
    else:
        untrusted_policies = sorted(policy_digests - trusted_policies)
        checks["wallet_governance_policy_trust_anchor"] = {
            "valid": not untrusted_policies,
            "pinned": True,
            "policy_sha256": ordered_policy_digests,
            "trusted_policy_sha256": sorted(trusted_policies),
            "untrusted_policy_sha256": untrusted_policies,
            "reason": (
                "every wallet governance policy matches the trusted allowlist"
                if not untrusted_policies
                else "wallet governance policy digest is not present in the trusted allowlist"
            ),
        }
        if untrusted_policies:
            return failure(checks["wallet_governance_policy_trust_anchor"]["reason"])

    historical_matches = []
    ordered_enrollments = sorted(
        snapshot_by_id.values(),
        key=lambda item: item["enrollment_id"],
    )
    for snapshot in ordered_enrollments:
        valid, reason, historical = resolve_historical_wallet_enrollment(
            ordered_history, snapshot, float(attested_at),
        )
        if not valid or historical is None:
            return failure(reason)
        if (
            snapshot.get("chain_id") == chain_id
            and snapshot.get("wallet_address") == wallet_address.lower()
            and historical.get("status") == "ACTIVE"
        ):
            historical_matches.append(historical)

    if len(historical_matches) != 1:
        return failure("wallet was not uniquely enrolled and active when the outcome was attested")
    return (
        True,
        "wallet enrollment governance state verified at attestation time",
        historical_matches[0],
        checks,
    )
