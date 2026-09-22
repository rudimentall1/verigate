"""Tests for SQLite storage and transactional guardrail accounting."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.models import Decision, GuardrailDecision, PaymentIntent
from core.storage import Storage


class StorageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        self.storage = Storage(self.db_path)

    def tearDown(self) -> None:
        self.storage.close()
        self.tmp.cleanup()

    def _intent(
        self,
        *,
        intent_id: str = "intent-1",
        agent_id: str = "agent-1",
        payee: str = "merchant",
        asset: str = "USDC",
        amount: float = 10.0,
    ) -> PaymentIntent:
        return PaymentIntent(
            intent_id=intent_id,
            agent_id=agent_id,
            payee=payee,
            asset=asset,
            network="base",
            amount=amount,
        )

    def _decision(
        self,
        intent: PaymentIntent,
        decision: Decision = Decision.ALLOW,
    ) -> GuardrailDecision:
        return GuardrailDecision(
            intent_id=intent.intent_id,
            agent_id=intent.agent_id,
            decision=decision,
            matched_rules=(),
        )

    def test_update_signature_attaches_to_existing_row(self) -> None:
        intent = self._intent()

        self.storage.record(
            intent,
            self._decision(intent),
            signature=None,
        )

        self.storage.update_signature(
            intent.intent_id,
            "test-signature",
        )

        row = self.storage._conn.execute(
            "SELECT signature FROM audit_log WHERE intent_id = ?",
            (intent.intent_id,),
        ).fetchone()

        self.assertEqual(row[0], "test-signature")
        self.assertEqual(self.storage.count_intent(intent.intent_id), 1)

    def test_update_signature_rejects_unknown_intent(self) -> None:
        with self.assertRaisesRegex(ValueError, "was not found"):
            self.storage.update_signature(
                "does-not-exist",
                "test-signature",
            )

    def test_engine_records_exactly_one_attempt(self) -> None:
        from core.engine import GuardrailEngine
        from core.policy import Policy

        policy = Policy.load("policies/default.yaml")
        engine = GuardrailEngine(policy, self.storage)

        intent = self._intent(
            intent_id="engine-single-record",
            amount=3.0,
        )

        decision = engine.evaluate(intent)

        self.assertIn(
            decision.decision,
            (Decision.ALLOW, Decision.WARN, Decision.BLOCK),
        )
        self.assertEqual(
            self.storage.count_intent(intent.intent_id),
            1,
        )

    def test_engine_record_can_receive_signature_without_second_audit_row(self) -> None:
        from core.engine import GuardrailEngine
        from core.policy import Policy

        policy = Policy.load("policies/default.yaml")
        engine = GuardrailEngine(policy, self.storage)

        intent = self._intent(
            intent_id="engine-signed-single-record",
            amount=3.0,
        )

        decision = engine.evaluate(intent)
        self.storage.update_signature(
            intent.intent_id,
            "signed-attestation",
        )

        row = self.storage._conn.execute(
            "SELECT decision, signature "
            "FROM audit_log WHERE intent_id = ?",
            (intent.intent_id,),
        ).fetchone()

        self.assertEqual(row[0], decision.decision.value)
        self.assertEqual(row[1], "signed-attestation")
        self.assertEqual(
            self.storage.count_intent(intent.intent_id),
            1,
        )

    def test_transaction_commits(self) -> None:
        intent = self._intent()

        with self.storage.transaction():
            self.storage.record(
                intent,
                self._decision(intent),
                signature=None,
                commit=False,
            )

        self.assertEqual(self.storage.calls_last_minute("agent-1"), 1)

    def test_transaction_rolls_back(self) -> None:
        intent = self._intent()

        with self.assertRaisesRegex(RuntimeError, "rollback"):
            with self.storage.transaction():
                self.storage.record(
                    intent,
                    self._decision(intent),
                    signature=None,
                    commit=False,
                )
                raise RuntimeError("rollback")

        self.assertEqual(self.storage.calls_last_minute("agent-1"), 0)

    def test_record_commit_false_is_not_visible_after_rollback(self) -> None:
        intent = self._intent()

        try:
            with self.storage.transaction():
                self.storage.record(
                    intent,
                    self._decision(intent),
                    signature=None,
                    commit=False,
                )
                raise ValueError("abort")
        except ValueError:
            pass

        self.assertFalse(
            self.storage.payee_seen_before(
                "agent-1",
                "merchant",
                "different-intent",
            )
        )

    def test_blocked_attempt_counts_for_rate_limit(self) -> None:
        intent = self._intent()

        self.storage.record(
            intent,
            self._decision(intent, Decision.BLOCK),
            signature=None,
        )

        self.assertEqual(self.storage.calls_last_minute("agent-1"), 1)

    def test_blocked_attempt_does_not_count_as_spend(self) -> None:
        intent = self._intent(amount=100.0)

        self.storage.record(
            intent,
            self._decision(intent, Decision.BLOCK),
            signature=None,
        )

        self.assertEqual(self.storage.spent_today("agent-1", "USDC"), 0.0)

    def test_allowed_attempt_counts_as_spend(self) -> None:
        intent = self._intent(amount=12.5)

        self.storage.record(
            intent,
            self._decision(intent, Decision.ALLOW),
            signature=None,
        )

        self.assertAlmostEqual(
            self.storage.spent_today("agent-1", "USDC"),
            12.5,
        )

    def test_warn_attempt_counts_as_spend(self) -> None:
        intent = self._intent(amount=7.5)

        self.storage.record(
            intent,
            self._decision(intent, Decision.WARN),
            signature=None,
        )

        self.assertAlmostEqual(
            self.storage.spent_today("agent-1", "USDC"),
            7.5,
        )

    def test_payee_is_seen_after_non_block_record(self) -> None:
        first = self._intent(
            intent_id="first",
            payee="merchant",
        )

        self.storage.record(
            first,
            self._decision(first, Decision.ALLOW),
            signature=None,
        )

        self.assertTrue(
            self.storage.payee_seen_before(
                "agent-1",
                "merchant",
                "second",
            )
        )

    def test_blocked_payee_does_not_make_payee_known(self) -> None:
        first = self._intent(
            intent_id="blocked",
            payee="merchant",
        )

        self.storage.record(
            first,
            self._decision(first, Decision.BLOCK),
            signature=None,
        )

        self.assertFalse(
            self.storage.payee_seen_before(
                "agent-1",
                "merchant",
                "second",
            )
        )

    def test_payee_is_scoped_to_agent(self) -> None:
        first = self._intent(
            intent_id="first",
            agent_id="agent-a",
            payee="merchant",
        )

        self.storage.record(
            first,
            self._decision(first),
            signature=None,
        )

        self.assertFalse(
            self.storage.payee_seen_before(
                "agent-b",
                "merchant",
                "second",
            )
        )

    def test_history_respects_limit(self) -> None:
        for index in range(3):
            intent = self._intent(
                intent_id=f"intent-{index}",
                amount=float(index + 1),
            )
            self.storage.record(
                intent,
                self._decision(intent),
                signature=None,
            )

        history = self.storage.history("agent-1", limit=2)

        self.assertEqual(len(history), 2)
        self.assertEqual(
            {item["intent_id"] for item in history},
            {"intent-1", "intent-2"},
        )

    def test_history_with_non_positive_limit_is_empty(self) -> None:
        intent = self._intent()

        self.storage.record(
            intent,
            self._decision(intent),
            signature=None,
        )

        self.assertEqual(self.storage.history("agent-1", limit=0), [])
        self.assertEqual(self.storage.history("agent-1", limit=-1), [])


if __name__ == "__main__":
    unittest.main()

