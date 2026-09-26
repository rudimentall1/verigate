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
from .authority_intent_graph import AuthorityAwareIntentGraph
from .authority_protocol import Authority, AuthorityState as GenesisAuthorityState
from .intent_graph import IntentGraphBuilder
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
        authority_service: DynamicAuthorityService | None = None,
    ):
        self.policy = policy
        self.storage = storage
        self.policy_source_ref = policy_source_ref
        self.require_governed_policy = require_governed_policy
        self.authority_service = authority_service or DynamicAuthorityService(storage)
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

    def _persist_authorization(
        self,
        artifacts: dict,
        intent_id: str,
        *,
        agent_signature: str | None = None,
    ) -> dict:
        """Persist immutable authorization artifacts for later evidence queries."""
        self.storage.record_authorization_artifacts(
            artifacts,
            agent_signature=agent_signature,
        )
        self.storage.update_signature(
            intent_id,
            artifacts["decision_receipt"]["signature"],
        )
        return artifacts

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
                context_digest=intent.context_digest,
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
                R.check_purpose_allowed,
                R.check_context_constraints,
                R.check_execution_graph,
                R.check_destination_allowed,
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
                context_digest=action.context_digest,
            )
            self.storage.record_action(action, decision, commit=False)
            return decision

    @staticmethod
    def _genesis_assessment(action, capability, authority):
        """Project proven runtime authority into the Genesis 2.0 protocol.

        This is a boundary adapter, not a second authority implementation:
        the existing capability/authority snapshot remains authoritative, while
        Genesis receives an immutable envelope and assessment for provenance.
        """
        if capability.identity_id is None:
            return None
        identity_id = capability.identity_id
        genesis_authority = Authority(
            authority_id=f"{action.agent_id}:{capability.capability_id}:{authority.ledger_head_hash or authority.digest}",
            agent_id=action.agent_id,
            identity_id=identity_id,
            capability_id=capability.capability_id,
            capability_version=capability.version,
            capability_sha256=capability.digest,
            state=GenesisAuthorityState(authority.state.value),
            multiplier=authority.multiplier,
            ledger_head_hash=authority.ledger_head_hash,
            effective_from=authority.evaluated_at,
            metadata={
                "source": "core.authority_state.AuthoritySnapshot",
                "successes": authority.successes,
                "adverse_events": authority.adverse_events,
                "critical_events": authority.critical_events,
                "reason": authority.reason,
            },
        )
        graph = (
            IntentGraphBuilder(graph_id=f"intent:{action.intent_id}")
            .add_action(action)
            .build()
        )
        return AuthorityAwareIntentGraph(
            graph, genesis_authority, capability
        ).assess(action.intent_id)

    def _authorize_control_plane(
        self,
        action: ActionIntent,
        private_key,
        *,
        capability_id: str | None = None,
        identity_id: str | None = None,
        agent_signature: str | None = None,
        decision: GuardrailDecision | None = None,
    ) -> dict:
        """Single authorization pipeline for every protocol adapter.

        Adapters may provide legacy payment inputs, but authorization issuance,
        policy evaluation, authority binding, and persistence happen here.
        """
        identity = None
        if identity_id is not None:
            if not agent_signature:
                raise ValueError("agent signature is required for identity-bound authorization")
            identity = IdentityRegistry(self.storage).authorize_action(
                identity_id,
                action,
                agent_signature,
            )

        if decision is None:
            decision = self.evaluate_action(action)

        capability = None
        authority = None
        # A denied action still gets a signed DecisionReceipt. Static/dynamic
        # authority is required only when the policy decision is ALLOW; a
        # denied request must never fail closed by disappearing as an error.
        if capability_id is not None and decision.decision == Decision.ALLOW:
            capability = CapabilityRegistry(self.storage).assert_authority(
                capability_id,
                action,
                identity_id=identity_id,
            )
            authority = self.authority_service.assert_action(
                capability,
                action,
            )

        authority_assessment = None
        if capability is not None and authority is not None:
            authority_assessment = self._genesis_assessment(
                action, capability, authority
            )

        artifacts = AuthorizationService().issue(
            action,
            decision,
            self.policy.digest,
            private_key,
            nonce=action.intent_id,
            capability=capability,
            identity=identity,
            authority=authority,
            authority_policy=self.authority_service.policy if authority is not None else None,
            policy=self.policy if capability is not None else None,
            signed_policy=self.signed_policy_version(private_key),
            authority_assessment=authority_assessment,
        )
        return self._persist_authorization(
            artifacts,
            action.intent_id,
            agent_signature=agent_signature,
        )

    def authorize_action(
        self,
        action: ActionIntent,
        capability_id: str,
        identity_id: str,
        agent_signature: str,
        private_key,
    ) -> dict:
        """Protocol-agnostic adapter into the single control-plane pipeline."""
        return self._authorize_control_plane(
            action,
            private_key,
            capability_id=capability_id,
            identity_id=identity_id,
            agent_signature=agent_signature,
        )

    def authorize(self, intent: PaymentIntent, private_key) -> dict:
        """Legacy payment decision endpoint; never mints execution authority.

        Executable authorization requires an explicit capability-bound control
        plane path via ``authorize_with_capability`` or ``authorize_with_identity``.
        """
        action = intent.as_action_intent()
        decision = self.evaluate(intent)
        artifacts = AuthorizationService().issue_decision_receipt(
            action,
            decision,
            self.policy.digest,
            private_key,
            signed_policy=self.signed_policy_version(private_key),
        )
        return self._persist_authorization(artifacts, intent.intent_id)

    def authorize_with_capability(
        self,
        intent: PaymentIntent,
        capability_id: str,
        private_key,
    ) -> dict:
        """Payment adapter with explicit static/dynamic authority binding."""
        return self._authorize_control_plane(
            intent.as_action_intent(),
            private_key,
            capability_id=capability_id,
            decision=self.evaluate(intent),
        )

    def authorize_with_identity(
        self,
        intent: PaymentIntent,
        capability_id: str,
        identity_id: str,
        agent_signature: str,
        private_key,
    ) -> dict:
        """Payment adapter with identity + capability authority binding."""
        return self._authorize_control_plane(
            intent.as_action_intent(),
            private_key,
            capability_id=capability_id,
            identity_id=identity_id,
            agent_signature=agent_signature,
            decision=self.evaluate(intent),
        )
