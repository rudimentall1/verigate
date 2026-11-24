"""Shared historical outcome-attestor verification for proof building and validation."""

from __future__ import annotations

import base64
import hashlib
import math
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.governance import GovernancePolicy, verify_governance_quorum
from core.proof_engine import canonical, digest


def verify_outcome_attestation_signature(
    attestation_data: dict[str, Any],
    attestor_data: dict[str, Any],
) -> tuple[bool, str]:
    """Verify the independent outcome signature against its registered key.

    Expiry and revocation are evaluated at attestation time so later governance
    changes do not retroactively invalidate an otherwise valid historical proof.
    """
    if not isinstance(attestation_data, dict) or attestation_data.get("algorithm") != "Ed25519":
        return False, "unsupported outcome attestation signature algorithm"
    attestation_payload = attestation_data.get("payload")
    if not isinstance(attestation_payload, dict):
        return False, "outcome attestation payload is malformed"

    attestor_id = attestation_payload.get("attestor_id")
    if attestor_id != attestor_data.get("attestor_id"):
        return False, "outcome attestation signer identity mismatch"

    registered_type = attestor_data.get("attestor_type")
    expected_type = (
        "EXECUTOR_SELF_REPORT"
        if registered_type == "EXECUTOR"
        else registered_type
    )
    if expected_type not in {"EXECUTOR_SELF_REPORT", "EXTERNAL_VERIFIER", "CHAIN_VERIFIER"}:
        return False, "registered outcome attestor type is invalid"
    if attestation_payload.get("attestor_type") != expected_type:
        return False, "outcome attestation type does not match registered attestor"

    attested_at = attestation_payload.get("attested_at")
    created_at = attestor_data.get("created_at")
    if (
        isinstance(attested_at, bool)
        or not isinstance(attested_at, (int, float))
        or not math.isfinite(float(attested_at))
        or isinstance(created_at, bool)
        or not isinstance(created_at, (int, float))
        or not math.isfinite(float(created_at))
        or float(attested_at) < float(created_at)
    ):
        return False, "outcome attestation time is invalid for registered attestor authority"

    for field, comparison in (("expires_at", "expiry"), ("revoked_at", "revocation")):
        boundary = attestor_data.get(field)
        if boundary is not None:
            if (
                isinstance(boundary, bool)
                or not isinstance(boundary, (int, float))
                or not math.isfinite(float(boundary))
            ):
                return False, f"registered attestor {comparison} time is invalid"
            if float(attested_at) >= float(boundary):
                return False, f"outcome attestor authority had {comparison} before attestation"

    public_key_b64 = attestor_data.get("public_key_b64")
    try:
        raw_public_key = base64.b64decode(public_key_b64, validate=True)
        if len(raw_public_key) != 32:
            raise ValueError("Ed25519 public key must be 32 bytes")
        if hashlib.sha256(raw_public_key).hexdigest() != attestor_data.get("key_id"):
            raise ValueError("registered attestor key fingerprint mismatch")
        public_key = Ed25519PublicKey.from_public_bytes(raw_public_key)
        signature = base64.b64decode(attestation_data.get("signature"), validate=True)
        public_key.verify(signature, canonical(attestation_payload))
    except (InvalidSignature, TypeError, ValueError):
        return False, "outcome attestation signature verification failed"
    return True, "outcome attestation signature and historical attestor authority verified"



def replay_attestor_governance_state(
    verified_actions: list[tuple[float, dict[str, Any]]],
    attestor_data: dict[str, Any],
    attested_at: float,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Replay quorum-approved registry changes and select the key at attested_at.

    The registry node is a snapshot, not the historical source of truth for
    every attestation. Governance actions determine both its final state and
    the key that was authorised when the signed outcome was produced.
    """
    if not verified_actions:
        return False, "attestor governance history is empty", None

    ordered_actions = sorted(verified_actions, key=lambda item: item[0])
    previous_time = None
    registered = False
    state = "UNREGISTERED"
    public_key_b64 = None
    key_id = None
    attestor_type = None
    expires_at = None
    revoked_at = None
    state_at_attestation = None

    for effective_at, action in ordered_actions:
        if previous_time is not None and effective_at <= previous_time:
            return False, "attestor governance actions have ambiguous or non-monotonic ordering", None
        previous_time = effective_at
        operation = action.get("action")

        if operation == "ATTESTOR_REGISTER":
            if registered:
                return False, "attestor governance history contains a duplicate registration", None
            next_key_b64 = action.get("public_key_b64")
            next_type = action.get("attestor_type")
            try:
                raw_key = base64.b64decode(next_key_b64, validate=True)
                if len(raw_key) != 32:
                    raise ValueError("Ed25519 key must be 32 bytes")
                if next_type not in {"EXECUTOR", "EXTERNAL_VERIFIER", "CHAIN_VERIFIER"}:
                    raise ValueError("invalid attestor type")
                next_expiry = action.get("attestor_expires_at")
                if next_expiry is not None and (
                    isinstance(next_expiry, bool)
                    or not isinstance(next_expiry, (int, float))
                    or not math.isfinite(float(next_expiry))
                ):
                    raise ValueError("invalid attestor expiry")
            except (TypeError, ValueError):
                return False, "attestor registration contains an invalid key, type or expiry", None
            registered = True
            state = "ACTIVE"
            public_key_b64 = next_key_b64
            key_id = hashlib.sha256(raw_key).hexdigest()
            attestor_type = next_type
            expires_at = next_expiry
            revoked_at = None

        elif operation == "ATTESTOR_ACTIVATE":
            if not registered:
                return False, "attestor activation precedes registration", None
            state = "ACTIVE"

        elif operation == "ATTESTOR_ROTATE":
            if not registered:
                return False, "attestor rotation precedes registration", None
            next_key_b64 = action.get("public_key_b64")
            next_type = action.get("attestor_type")
            try:
                raw_key = base64.b64decode(next_key_b64, validate=True)
                if len(raw_key) != 32:
                    raise ValueError("Ed25519 key must be 32 bytes")
                if next_type not in {"EXECUTOR", "EXTERNAL_VERIFIER", "CHAIN_VERIFIER"}:
                    raise ValueError("invalid attestor type")
                next_expiry = action.get("attestor_expires_at")
                if next_expiry is not None and (
                    isinstance(next_expiry, bool)
                    or not isinstance(next_expiry, (int, float))
                    or not math.isfinite(float(next_expiry))
                ):
                    raise ValueError("invalid attestor expiry")
            except (TypeError, ValueError):
                return False, "attestor rotation contains an invalid key, type or expiry", None
            state = "ACTIVE"
            public_key_b64 = next_key_b64
            key_id = hashlib.sha256(raw_key).hexdigest()
            attestor_type = next_type
            expires_at = next_expiry
            revoked_at = None

        elif operation == "ATTESTOR_REVOKE":
            if not registered or state != "ACTIVE":
                return False, "attestor revocation does not follow an active registration", None
            state = "REVOKED"
            revoked_at = effective_at

        elif operation == "ATTESTOR_EXPIRE":
            if not registered:
                return False, "attestor expiry precedes registration", None
            state = "EXPIRED"

        else:
            return False, "unsupported attestor governance state transition", None

        if effective_at <= attested_at:
            state_at_attestation = {
                "status": state,
                "public_key_b64": public_key_b64,
                "key_id": key_id,
                "attestor_type": attestor_type,
                "expires_at": expires_at,
                "revoked_at": revoked_at,
            }

    if not registered:
        return False, "attestor governance history has no registration", None

    if (
        attestor_data.get("status") != state
        or attestor_data.get("public_key_b64") != public_key_b64
        or attestor_data.get("key_id") != key_id
        or attestor_data.get("attestor_type") != attestor_type
        or attestor_data.get("expires_at") != expires_at
        or bool(attestor_data.get("revoked_at")) != bool(revoked_at)
    ):
        return False, "attestor registry snapshot does not match replayed governance state", None

    if state_at_attestation is None:
        return False, "attestor was not registered when the outcome was attested", None
    if state_at_attestation["status"] != "ACTIVE":
        return False, "attestor was not active when the outcome was attested", None

    historical_attestor = dict(attestor_data)
    historical_attestor.update(state_at_attestation)
    if historical_attestor.get("status") == "ACTIVE":
        # Storage keeps revoked_at as an audit marker after explicit reactivation.
        # It is not an active revocation boundary once governance restored ACTIVE.
        historical_attestor["revoked_at"] = None
    return True, "attestor governance state and historical key verified", historical_attestor




def resolve_historical_attestor(
    governance_history: list[dict[str, Any]],
    attestor_data: dict[str, Any],
    attested_at: float,
) -> tuple[bool, str, dict[str, Any] | None]:
    """Verify stored governance envelopes and resolve the key active at attestation time.

    Legacy/bootstrap attestors without governance history remain supported only
    while their registry snapshot is currently ACTIVE. Governed attestors are
    resolved exclusively from their verified, quorum-approved action history.
    """
    if (
        isinstance(attested_at, bool)
        or not isinstance(attested_at, (int, float))
        or not math.isfinite(float(attested_at))
    ):
        return False, "outcome attestation timestamp is invalid", None

    if not isinstance(attestor_data, dict):
        return False, "attestor registry snapshot is malformed", None

    if not governance_history:
        if attestor_data.get("status") != "ACTIVE":
            return False, "bootstrap outcome attestor is not currently active", None
        return True, "active bootstrap attestor snapshot resolved", dict(attestor_data)

    if not isinstance(governance_history, list):
        return False, "attestor governance history is malformed", None

    verified_actions: list[tuple[float, dict[str, Any]]] = []
    seen_action_ids: set[str] = set()

    for envelope in governance_history:
        if not isinstance(envelope, dict):
            return False, "attestor governance envelope is malformed", None
        action = envelope.get("action") or envelope.get("governance_action")
        approvals = envelope.get("approvals")
        policy_data = envelope.get("governance_policy") or envelope.get("policy")
        if not isinstance(action, dict) or not isinstance(policy_data, dict):
            return False, "attestor governance envelope is incomplete", None
        if not isinstance(approvals, list) or not approvals:
            return False, "attestor governance action has no approval evidence", None

        action_id = action.get("action_id")
        if (
            not isinstance(action_id, str)
            or not action_id
            or action_id in seen_action_ids
        ):
            return False, "attestor governance action identity is missing or duplicated", None
        seen_action_ids.add(action_id)
        if action.get("attestor_id") != attestor_data.get("attestor_id"):
            return False, "attestor governance action targets a different attestor", None

        action_issued_at = action.get("issued_at")
        if (
            isinstance(action_issued_at, bool)
            or not isinstance(action_issued_at, (int, float))
            or not math.isfinite(float(action_issued_at))
        ):
            return False, "attestor governance action issue time is invalid", None

        approval_ids: set[str] = set()
        approval_issue_times: list[float] = []
        for approval in approvals:
            approval_payload = approval.get("payload") if isinstance(approval, dict) else None
            approval_id = (
                approval_payload.get("approval_id")
                if isinstance(approval_payload, dict)
                else None
            )
            issued_at = (
                approval_payload.get("issued_at")
                if isinstance(approval_payload, dict)
                else None
            )
            if (
                not isinstance(approval_id, str)
                or not approval_id
                or approval_id in approval_ids
            ):
                return False, "governance approval identity is missing or duplicated", None
            if (
                isinstance(issued_at, bool)
                or not isinstance(issued_at, (int, float))
                or not math.isfinite(float(issued_at))
            ):
                return False, "governance approval issue time is invalid", None
            approval_ids.add(approval_id)
            approval_issue_times.append(float(issued_at))

        verification_time = max(
            [float(action_issued_at), *approval_issue_times]
        )
        try:
            policy = GovernancePolicy.from_dict(policy_data)
            if policy.digest != action.get("governance_policy_sha256"):
                return False, "governance action policy fingerprint does not match policy evidence", None
            envelope_policy_digest = envelope.get("governance_policy_sha256")
            if envelope_policy_digest is not None and envelope_policy_digest != policy.digest:
                return False, "governance envelope policy fingerprint mismatch", None
            envelope_action_digest = envelope.get("action_sha256")
            if envelope_action_digest is not None and envelope_action_digest != digest(action):
                return False, "governance envelope action fingerprint mismatch", None
            valid_quorum, quorum_reason = verify_governance_quorum(
                action,
                approvals,
                policy,
                now=verification_time,
            )
        except (TypeError, ValueError, KeyError) as exc:
            return False, f"invalid attestor governance quorum evidence: {exc}", None
        if not valid_quorum:
            return False, f"attestor governance quorum verification failed: {quorum_reason}", None
        verified_actions.append((verification_time, action))

    return replay_attestor_governance_state(
        verified_actions,
        attestor_data,
        float(attested_at),
    )
