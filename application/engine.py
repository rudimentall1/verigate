"""Application composition of core policy evaluation and attestation issuance."""
from __future__ import annotations

from typing import Any

from attest.authorization import AuthorizationService
from core.authorization import AuthorizationArtifactIssuer
from core.engine import GuardrailEngine as CoreGuardrailEngine
from core.models import PaymentIntent
from core.policy import Policy
from core.storage import Storage


class GuardrailEngine(CoreGuardrailEngine):
    """Guardrail runtime with the attestation issuer wired at the app boundary.

    Core keeps policy evaluation and durable decision flow independent from the
    cryptographic attestation implementation. Applications use this composition
    root when signed receipts or executable authorizations are required.
    """

    def __init__(
        self,
        policy: Policy,
        storage: Storage,
        *,
        authorization_service: AuthorizationArtifactIssuer | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            policy,
            storage,
            authorization_service=authorization_service or AuthorizationService(),
            **kwargs,
        )
