"""GuardrailEngine — orchestrates rule evaluation, storage lookups, and
produces a final GuardrailDecision.

The engine is the single owner of the evaluate -> persist flow.
"""

from __future__ import annotations

from . import rules as R
from .models import ActionIntent, Decision, GuardrailDecision, PaymentIntent, RuleMatch, Severity
from .policy import Policy
from .storage import Storage

from .authorization import AuthorizationService
from .capabilities import CapabilityRegistry
from .identity import IdentityRegistry


class GuardrailEngine:
    def __init__(self, policy: Policy, storage: Storage):
        self.policy = policy
        self.storage = storage

    def evaluate(self, intent: PaymentIntent) -> GuardrailDecision:
        """Evaluate and persist one payment atomically.

        The transaction covers:
        1. state reads used by policy rules;
        2. final decision calculation;
        3. audit recording.

        BLOCK attempts are recorded for rate limiting but are excluded from
        spend and first-seen-payee accounting by Storage.
        """
        with self.storage.transaction():
            matches: list[RuleMatch] = []

            for check in (
                R.check_blocked_payee,
                R.check_payee_allowlist,
                R.check_network_allowed,
                R.check_asset_allowed,
                R.check_per_tx_cap,
            ):
                match = check(intent, self.policy)
                if match:
                    matches.append(match)

            payee_seen = self.storage.payee_seen_before(
                intent.agent_id,
                intent.payee,
                intent.intent_id,
            )

            match = R.check_new_payee_cap(
                intent,
                self.policy,
                payee_seen,
            )
            if match:
                matches.append(match)

            spent_today = self.storage.spent_today(
                intent.agent_id,
                intent.asset,
            )

            match = R.check_daily_cap(
                intent,
                self.policy,
                spent_today,
            )
            if match:
                matches.append(match)

            match = R.check_confirmation_threshold(
                intent,
                self.policy,
            )
            if match:
                matches.append(match)

            calls = self.storage.calls_last_minute(intent.agent_id)

            match = R.check_rate_limit(
                self.policy,
                calls,
            )
            if match:
                matches.append(match)

            if any(match.severity == Severity.BLOCK for match in matches):
                final = Decision.BLOCK
            elif any(match.severity == Severity.WARN for match in matches):
                final = Decision.WARN
            else:
                final = Decision.ALLOW

            decision = GuardrailDecision(
                intent_id=intent.intent_id,
                agent_id=intent.agent_id,
                decision=final,
                matched_rules=tuple(matches),
            )

            # IMPORTANT:
            # evaluate() is now responsible for exactly one audit record.
            # Callers must NOT call storage.record() again.
            self.storage.record(
                intent,
                decision,
                signature=None,
                commit=False,
            )

            return decision


    def authorize(self, intent: PaymentIntent, private_key) -> dict:
        """Legacy authorization path retained for compatibility."""
        decision = self.evaluate(intent)
        action = intent.as_action_intent()
        artifacts = AuthorizationService().issue(
            action,
            decision,
            self.policy.digest,
            private_key,
            nonce=intent.intent_id,
        )
        self.storage.update_signature(intent.intent_id, artifacts["decision_receipt"]["signature"])
        return artifacts

    def authorize_with_capability(
        self,
        intent: PaymentIntent,
        capability_id: str,
        private_key,
    ) -> dict:
        """Canonical capability-bound path retained for compatible callers."""
        decision = self.evaluate(intent)
        action = intent.as_action_intent()
        capability = CapabilityRegistry(self.storage).assert_authority(capability_id, action)
        artifacts = AuthorizationService().issue(
            action,
            decision,
            self.policy.digest,
            private_key,
            nonce=intent.intent_id,
            capability=capability,
        )
        self.storage.update_signature(intent.intent_id, artifacts["decision_receipt"]["signature"])
        return artifacts

    def authorize_with_identity(
        self,
        intent: PaymentIntent,
        capability_id: str,
        identity_id: str,
        agent_signature: str,
        private_key,
    ) -> dict:
        """Canonical identity + capability authority path."""
        action = intent.as_action_intent()
        identity = IdentityRegistry(self.storage).authorize_action(
            identity_id,
            action,
            agent_signature,
        )
        decision = self.evaluate(intent)
        capability = CapabilityRegistry(self.storage).assert_authority(
            capability_id,
            action,
            identity_id=identity_id,
        )
        artifacts = AuthorizationService().issue(
            action,
            decision,
            self.policy.digest,
            private_key,
            nonce=intent.intent_id,
            capability=capability,
            identity=identity,
        )
        self.storage.update_signature(intent.intent_id, artifacts["decision_receipt"]["signature"])
        return artifacts
