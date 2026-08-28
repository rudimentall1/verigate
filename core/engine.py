"""GuardrailEngine — orchestrates rule evaluation, storage lookups, and
produces a final GuardrailDecision. This is the single place that decides
BLOCK beats WARN beats ALLOW.
"""
from __future__ import annotations

from . import rules as R
from .models import Decision, GuardrailDecision, PaymentIntent, RuleMatch, Severity
from .policy import Policy
from .storage import Storage


class GuardrailEngine:
    def __init__(self, policy: Policy, storage: Storage):
        self.policy = policy
        self.storage = storage

    def evaluate(self, intent: PaymentIntent) -> GuardrailDecision:
        matches: list[RuleMatch] = []

        for check in (
            R.check_blocked_payee,
            R.check_payee_allowlist,
            R.check_network_allowed,
            R.check_asset_allowed,
            R.check_per_tx_cap,
        ):
            m = check(intent, self.policy)
            if m:
                matches.append(m)

        payee_seen = self.storage.payee_seen_before(intent.agent_id, intent.payee, intent.intent_id)
        m = R.check_new_payee_cap(intent, self.policy, payee_seen)
        if m:
            matches.append(m)

        spent_today = self.storage.spent_today(intent.agent_id, intent.asset)
        m = R.check_daily_cap(intent, self.policy, spent_today)
        if m:
            matches.append(m)

        m = R.check_confirmation_threshold(intent, self.policy)
        if m:
            matches.append(m)

        calls = self.storage.calls_last_minute(intent.agent_id)
        m = R.check_rate_limit(self.policy, calls)
        if m:
            matches.append(m)

        if any(m.severity == Severity.BLOCK for m in matches):
            final = Decision.BLOCK
        elif any(m.severity == Severity.WARN for m in matches):
            final = Decision.WARN
        else:
            final = Decision.ALLOW

        return GuardrailDecision(
            intent_id=intent.intent_id,
            agent_id=intent.agent_id,
            decision=final,
            matched_rules=tuple(matches),
        )
