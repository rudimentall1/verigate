"""Sign a GuardrailDecision so a third party can verify it independently.

The design contract: anyone holding the issuer's PUBLIC key can verify a
decision was genuinely produced by that issuer and has not been altered
since — without access to the issuer's server, database, or logs. Trust
moves from "believe our dashboard" to "check the math."
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.models import GuardrailDecision


def canonical_payload(decision: GuardrailDecision) -> bytes:
    """Deterministic JSON serialization — same decision always produces the
    same bytes, which is what makes signature verification meaningful."""
    payload = decision.as_dict()
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class SignedAttestation:
    payload: dict
    signature_b64: str
    algorithm: str = "Ed25519"

    def as_dict(self) -> dict:
        return {
            "payload": self.payload,
            "signature": self.signature_b64,
            "algorithm": self.algorithm,
        }


def sign_decision(decision: GuardrailDecision, private_key: Ed25519PrivateKey) -> SignedAttestation:
    payload_bytes = canonical_payload(decision)
    signature = private_key.sign(payload_bytes)
    return SignedAttestation(
        payload=json.loads(payload_bytes),
        signature_b64=base64.b64encode(signature).decode("ascii"),
    )
