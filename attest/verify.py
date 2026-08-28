"""Independent verification of a signed attestation. Requires only the
issuer's PUBLIC key — no server access, no API call to the issuer, no
trust in whoever is presenting the attestation to you.
"""
from __future__ import annotations

import base64
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def verify_attestation(attestation: dict, public_key: Ed25519PublicKey) -> tuple[bool, str]:
    """Returns (is_valid, reason). Never raises on a bad signature — a
    forged or tampered attestation is an expected input, not an error."""
    try:
        payload = attestation["payload"]
        signature_b64 = attestation["signature"]
    except KeyError as exc:
        return False, f"malformed attestation, missing field: {exc}"

    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    try:
        signature = base64.b64decode(signature_b64)
    except Exception:
        return False, "signature is not valid base64"

    try:
        public_key.verify(signature, payload_bytes)
    except InvalidSignature:
        return False, "signature does not match payload — tampered or forged"

    return True, "signature valid — this decision was genuinely issued and has not been altered"
