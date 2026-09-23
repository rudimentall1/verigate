"""Protocol-agnostic authorization artifact minting.

Policy evaluation can remain vertical-specific, while every integration uses
this same cryptographic path to turn a decision into portable proof and, for
ALLOW, a one-time execution capability.
"""
from __future__ import annotations

from typing import Any

from .models import ActionIntent, Capability, Decision, GuardrailDecision
from attest.receipt import issue_execution_authorization, sign_receipt


class AuthorizationService:
    """Mint decision receipts and execution capabilities for any action."""

    def issue(
        self,
        action: ActionIntent,
        decision: GuardrailDecision,
        policy_digest: str,
        private_key: Any,
        *,
        nonce: str | None = None,
        ttl_seconds: int = 300,
        capability: Capability | None = None,
    ) -> dict[str, Any]:
        if action.intent_id != decision.intent_id or action.agent_id != decision.agent_id:
            raise ValueError("action and decision identities do not match")

        # A capability is the authority source for the exact action. Keep the
        # optional parameter during migration so existing integrations remain
        # compatible while new control-plane flows can require it.
        if capability is not None:
            permitted, reason = capability.permits(action)
            if not permitted:
                raise PermissionError(reason)

        receipt = sign_receipt(action, decision, policy_digest, private_key)
        execution = None
        if decision.decision == Decision.ALLOW:
            execution = issue_execution_authorization(
                receipt,
                private_key,
                nonce=nonce or action.intent_id,
                ttl_seconds=ttl_seconds,
                capability_id=capability.capability_id if capability else None,
                capability_version=capability.version if capability else None,
            )

        return {
            "decision_receipt": receipt.as_dict(),
            "execution_authorization": execution.as_dict() if execution else None,
        }
