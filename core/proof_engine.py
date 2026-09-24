"""Generic verification pipeline for signed Verigate proof envelopes."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


@dataclass(frozen=True)
class ProofVerification:
    valid: bool
    reason: str
    root_digest: str | None = None
    invalid_evidence: tuple[str, ...] = ()
    assurance: dict[str, Any] | None = None


def verify_signed_proof(
    manifest: dict[str, Any],
    *,
    trusted_public_key_b64: str | None,
    node_validator: Callable[[dict[str, Any]], tuple[bool, str]],
    profile_validator: Callable[[dict[str, Any], str], tuple[bool, str]],
    root_calculator: Callable[[dict[str, Any]], str],
    assurance_claims: Callable[[str], list[str]],
) -> ProofVerification:
    """Run invariant envelope verification around profile semantics.

    Profile-specific semantics stay behind profile_validator; this engine
    owns envelope, graph, root, signature, and evidence verification order.
    """
    if not isinstance(manifest, dict):
        return ProofVerification(False, "manifest must be an object")

    payload = manifest.get("payload")
    signature = manifest.get("signature")
    embedded = manifest.get("issuer_public_key_b64")
    if not isinstance(payload, dict) or not isinstance(signature, str) or not isinstance(embedded, str):
        return ProofVerification(False, "manifest envelope is incomplete")
    if payload.get("manifest_version") != 1:
        return ProofVerification(False, "unsupported manifest version")

    graph_ok, graph_reason = node_validator(payload)
    if not graph_ok:
        return ProofVerification(False, graph_reason)

    profile = payload.get("proof_profile", "integrity")
    profile_ok, profile_reason = profile_validator(payload, profile)
    if not profile_ok:
        return ProofVerification(False, profile_reason)

    expected_root = root_calculator(payload)
    if payload.get("root_digest") != expected_root:
        return ProofVerification(False, "evidence Merkle root mismatch", expected_root)

    try:
        raw = base64.b64decode(embedded, validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError, TypeError):
        return ProofVerification(False, "invalid embedded issuer public key", expected_root)

    if trusted_public_key_b64 is not None and trusted_public_key_b64 != embedded:
        return ProofVerification(False, "issuer public key is not trusted", expected_root)

    try:
        public_key.verify(base64.b64decode(signature, validate=True), _canonical(payload))
    except (InvalidSignature, ValueError, TypeError):
        return ProofVerification(False, "invalid manifest signature", expected_root)

    verification = payload.get("verification") or {}
    invalid_evidence = tuple(
        key for key, item in verification.items()
        if isinstance(item, dict) and item.get("valid") is False
    )
    if invalid_evidence:
        return ProofVerification(
            False,
            "evidence verification failed",
            expected_root,
            invalid_evidence,
        )

    return ProofVerification(
        True,
        "valid signed evidence manifest",
        expected_root,
        (),
        {
            "profile": profile,
            "claims": assurance_claims(profile),
        },
    )


def _canonical(value: Any) -> bytes:
    import json
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
