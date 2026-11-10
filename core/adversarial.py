"""Adversarial verification plane for Verigate authority artifacts.

The corpus treats an ExecutionAuthorization as hostile input and mutates one
security-critical field at a time. Every mutation must fail independently at
the verification boundary. This is a regression corpus, not a risk score.
"""
from __future__ import annotations

import base64
import copy
from dataclasses import dataclass
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from attest.receipt import verify_execution_authorization


@dataclass(frozen=True)
class AttackResult:
    attack_id: str
    passed: bool
    description: str
    reason: str


@dataclass(frozen=True)
class AttackCase:
    attack_id: str
    description: str
    mutate: Callable[[dict[str, Any]], None]


class AdversarialVerificationPlane:
    """Black-box challenge harness for signed execution authority."""
    @staticmethod
    def cases() -> tuple[AttackCase, ...]:
        return (
            AttackCase(
                "AUTH-ACTION-TAMPER",
                "Change the exact authorized target without changing its signature.",
                lambda auth: auth["payload"]["action"].update(target="attacker"),
            ),
            AttackCase(
                "AUTH-AMOUNT-ESCALATION",
                "Increase the authorized amount after authority was issued.",
                lambda auth: auth["payload"]["action"].update(amount=10**12),
            ),
            AttackCase(
                "AUTH-CAPABILITY-SWAP",
                "Replace the capability identity with another capability.",
                lambda auth: auth["payload"].update(
                    capability_id="capability-attacker",
                    capability_sha256="f" * 64,
                ),
            ),
            AttackCase(
                "AUTH-IDENTITY-SWAP",
                "Replace the cryptographic identity provenance.",
                lambda auth: auth["payload"].update(
                    identity_id="identity-attacker",
                    identity_sha256="f" * 64,
                ),
            ),
            AttackCase(
                "AUTH-AUTHORITY-ESCALATION",
                "Raise a bounded dynamic multiplier to full authority.",
                lambda auth: auth["payload"].update(authority_multiplier=1.0),
            ),
            AttackCase(
                "AUTH-STATE-TAMPER",
                "Replace PROBATION/STANDARD/ELEVATED authority state metadata.",
                lambda auth: auth["payload"]["authority_state"].update(
                    state="ELEVATED"
                ),
            ),
            AttackCase(
                "AUTH-NONCE-SWAP",
                "Change the replay-protection nonce.",
                lambda auth: auth["payload"].update(nonce="attacker-nonce"),
            ),
            AttackCase(
                "AUTH-EXPIRY-EXTENSION",
                "Extend the authorization lifetime after signing.",
                lambda auth: auth["payload"].update(
                    expires_at=auth["payload"]["expires_at"] + 365 * 24 * 3600
                ),
            ),
            AttackCase(
                "AUTH-ID-TAMPER",
                "Replace the authorization identifier.",
                lambda auth: auth["payload"].update(
                    authorization_id="0" * 64
                ),
            ),
            AttackCase(
                "AUTH-SIGNATURE-TAMPER",
                "Corrupt the Ed25519 signature itself.",
                lambda auth: auth.update(
                    signature=base64.b64encode(b"tampered").decode("ascii")
                ),
            ),
        )

    @classmethod
    def run(
        cls,
        authorization: dict[str, Any],
        public_key: Ed25519PublicKey,
    ) -> list[AttackResult]:
        results: list[AttackResult] = []
        for case in cls.cases():
            mutated = copy.deepcopy(authorization)
            case.mutate(mutated)
            valid, reason = verify_execution_authorization(mutated, public_key)
            results.append(
                AttackResult(
                    attack_id=case.attack_id,
                    passed=not valid,
                    description=case.description,
                    reason=reason,
                )
            )
        return results

    @classmethod
    def assert_all_blocked(
        cls,
        authorization: dict[str, Any],
        public_key: Ed25519PublicKey,
    ) -> list[AttackResult]:
        results = cls.run(authorization, public_key)
        failed = [result for result in results if not result.passed]
        if failed:
            details = "; ".join(
                f"{item.attack_id}: {item.reason}" for item in failed
            )
            raise AssertionError(
                f"adversarial verification failure: {details}"
            )
        return results
