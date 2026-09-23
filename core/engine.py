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
from .authority_state import DynamicAuthorityService
from .capabilities import CapabilityRegistry
from .identity import IdentityRegistry
from .policy_version import build_policy_version, sign_policy_version


class GuardrailEngine:
    def __init__(
        self,
        policy: Policy,
        storage: Storage,
        *,
        policy_source_ref: str = "verigate:runtime",
        policy_version_number: int | None = None,
        policy_parent_sha256: str | None = None,
        require_governed_policy: bool = False,
    ):
        self.policy = policy
        self.storage = storage
        self.policy_source_ref = policy_source_ref
        self.require_governed_policy = require_governed_policy
        self.policy_version_number = (
            policy_version_number
            if policy_version_number is not None
            else int(policy.raw.get("_verigate_version", 1) or 1)
        )
        self.policy_parent_sha256 = policy_parent_sha256
        self._signed_policy_version = None

    def _assert_governed_policy_control(self) -> None:
        governed = self.storage.governed_policy_change_by_sha(self.policy.digest)
        if governed is None:
            raise PermissionError("policy version is not governance-approved")
        governed_policy = governed["policy_version"]["payload"]
        if (
            governed_policy["policy_sha256"] != self.policy.digest
            or governed_policy["version"] != self.policy_version_number
            or governed_policy["source_ref"] != self.policy_source_ref
            or governed_policy.get("parent_sha256") != self.policy_parent_sha256
        ):
            raise PermissionError("governed policy artifact does not match active policy")
        control = self.storage.policy_control(governed_policy["policy_id"])
        if control is not None:
            if control["frozen"]:
                raise PermissionError("governed policy is frozen")
            if control["active_policy_sha256"] != self.policy.digest:
                raise PermissionError("policy is not the active governed policy")

    def signed_policy_version(self, private_key) -> dict:
        if self._signed_policy_version is None:
            version = build_policy_version(
                self.policy,
                source_ref=self.policy_source_ref,
                version=self.policy_version_number,
                parent_sha256=self.policy_parent_sha256,
            )
            self._signed_policy_version = sign_policy_version(
                version,
                private_key,
            ).as_dict()
            self.storage.register_policy_version(self._signed_policy_version)
        if self.require_governed_policy:
            try:
                self._assert_governed_policy_control()
            except PermissionError:
                self._signed_policy_version = None
                raise
        return self._signed_policy_version

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


    def evaluate_action(self, action: ActionIntent) -> GuardrailDecision:
        """Evaluate any consequential agent action, independent of protocol."""
        with self.storage.transaction():
            matches: list[RuleMatch] = []
            for check in (
                R.check_action_type_allowed,
                R.check_target_allowed,
                R.check_generic_network_allowed,
                R.check_generic_asset_allowed,
                R.check_generic_amount_cap,
            ):
                match = check(action, self.policy)
                if match:
                    matches.append(match)

            calls = self.storage.calls_last_minute(action.agent_id)
            match = R.check_rate_limit(self.policy, calls)
            if match:
                matches.append(match)

            if any(match.severity == Severity.BLOCK for match in matches):
                final = Decision.BLOCK
            elif any(match.severity == Severity.WARN for match in matches):
                final = Decision.WARN
            else:
                final = Decision.ALLOW

            decision = GuardrailDecision(
                intent_id=action.intent_id,
                agent_id=action.agent_id,
                decision=final,
                matched_rules=tuple(matches),
            )
            self.storage.record_action(action, decision, commit=False)
            return decision

    def authorize_action(
        self,
        action: ActionIntent,
        capability_id: str,
        identity_id: str,
        agent_signature: str,
        private_key,
    ) -> dict:
        """Canonical control-plane authorization for a non-payment action."""
        identity = IdentityRegistry(self.storage).authorize_action(
            identity_id,
            action,
            agent_signature,
        )
        decision = self.evaluate_action(action)
        capability = CapabilityRegistry(self.storage).assert_authority(
            capability_id,
            action,
            identity_id=identity_id,
        )
        authority = DynamicAuthorityService(self.storage).assert_action(capability, action)
        artifacts = AuthorizationService().issue(
            action,
            decision,
            self.policy.digest,
            private_key,
            nonce=action.intent_id,
            capability=capability,
            identity=identity,
            authority=authority,
            signed_policy=self.signed_policy_version(private_key),
        )
        self.storage.update_signature(action.intent_id, artifacts["decision_receipt"]["signature"])
        return artifacts

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
            signed_policy=self.signed_policy_version(private_key),
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
        authority = DynamicAuthorityService(self.storage).assert_action(capability, action)
        artifacts = AuthorizationService().issue(
            action,
            decision,
            self.policy.digest,
            private_key,
            nonce=intent.intent_id,
            capability=capability,
            authority=authority,
            signed_policy=self.signed_policy_version(private_key),
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
        authority = DynamicAuthorityService(self.storage).assert_action(capability, action)
        artifacts = AuthorizationService().issue(
            action,
            decision,
            self.policy.digest,
            private_key,
            nonce=intent.intent_id,
            capability=capability,
            identity=identity,
            authority=authority,
            signed_policy=self.signed_policy_version(private_key),
        )
        self.storage.update_signature(intent.intent_id, artifacts["decision_receipt"]["signature"])
        return artifacts
