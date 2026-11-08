import os
import tempfile
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor

from core.engine import GuardrailEngine
from core.models import Decision, PaymentIntent, RuleMatch, Severity
from core.policy import Policy
from core.storage import Storage

POLICY_YAML = """
blocked_payees:
  - "0xBadActor"
allowed_networks:
  - base
allowed_assets:
  - USDC
per_tx_cap:
  USDC: 500
new_payee_cap:
  USDC: 50
daily_cap:
  USDC: 2000
confirmation_required_over:
  USDC: 250
rate_limit_per_minute: 5
"""


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        policy_path = os.path.join(self.tmpdir, "policy.yaml")
        with open(policy_path, "w") as fh:
            fh.write(POLICY_YAML)
        self.policy = Policy.load(policy_path)
        self.db_path = os.path.join(self.tmpdir, "audit.db")
        self.storage = Storage(self.db_path)
        self.engine = GuardrailEngine(self.policy, self.storage)

    def tearDown(self):
        self.storage.close()

    def _intent(self, **overrides):
        defaults = dict(
            agent_id="agent-1", payee="0xMerchant", asset="USDC", network="base", amount=10.0
        )
        defaults.update(overrides)
        return PaymentIntent(**defaults)

    def test_allows_small_first_payment_under_new_payee_cap(self):
        d = self.engine.evaluate(self._intent(amount=10.0))
        self.assertEqual(d.decision, Decision.ALLOW)

    def test_blocks_blocklisted_payee(self):
        d = self.engine.evaluate(self._intent(payee="0xBadActor", amount=1.0))
        self.assertEqual(d.decision, Decision.BLOCK)
        self.assertTrue(any(m.rule_id == "blocked_payee" for m in d.matched_rules))

    def test_blocks_over_per_tx_cap(self):
        d = self.engine.evaluate(self._intent(amount=600.0))
        self.assertEqual(d.decision, Decision.BLOCK)
        self.assertTrue(any(m.rule_id == "per_tx_cap_exceeded" for m in d.matched_rules))

    def test_blocks_disallowed_network(self):
        d = self.engine.evaluate(self._intent(network="ethereum-classic", amount=1.0))
        self.assertEqual(d.decision, Decision.BLOCK)
        self.assertTrue(any(m.rule_id == "network_not_allowed" for m in d.matched_rules))

    def test_warns_new_payee_over_new_payee_cap(self):
        d = self.engine.evaluate(self._intent(payee="0xNeverPaidBefore", amount=60.0))
        self.assertEqual(d.decision, Decision.WARN)
        self.assertTrue(any(m.rule_id == "new_payee_cap_exceeded" for m in d.matched_rules))

    def test_known_payee_bypasses_new_payee_cap(self):
        first = self._intent(payee="0xRepeatMerchant", amount=10.0)
        d1 = self.engine.evaluate(first)

        second = self._intent(payee="0xRepeatMerchant", amount=60.0)
        d2 = self.engine.evaluate(second)
        # Known payee -> new_payee_cap no longer applies, but this amount
        # is still under confirmation_required_over (250) and per_tx_cap,
        # so it should be a clean ALLOW.
        self.assertEqual(d2.decision, Decision.ALLOW)

    def test_warns_over_confirmation_threshold(self):
        d = self.engine.evaluate(self._intent(amount=300.0))
        self.assertEqual(d.decision, Decision.WARN)
        self.assertTrue(any(m.rule_id == "confirmation_required" for m in d.matched_rules))

    def test_blocks_over_daily_cap(self):
        # Daily-cap accumulation needs several prior payments, each under
        # per_tx_cap (500) to avoid being BLOCKed (and thus excluded from
        # the running total), without tripping the separate rate-limit
        # rule — so this test uses its own policy with a generous rate
        # limit, isolating the one rule under test.
        policy_path = os.path.join(self.tmpdir, "daily_cap_policy.yaml")
        with open(policy_path, "w") as fh:
            fh.write(POLICY_YAML.replace("rate_limit_per_minute: 5", "rate_limit_per_minute: 50").replace("confirmation_required_over:\n  USDC: 250", "confirmation_required_over:\n  USDC: 500"))
        policy = Policy.load(policy_path)
        engine = GuardrailEngine(policy, self.storage)

        established = self._intent(payee="0xRepeatMerchant", amount=10.0)
        d0 = engine.evaluate(established)
        self.assertEqual(d0.decision, Decision.ALLOW)

        for _ in range(4):
            top_up = self._intent(payee="0xRepeatMerchant", amount=495.0)
            d = engine.evaluate(top_up)
            self.assertEqual(d.decision, Decision.ALLOW)
        # evaluate() records each row once inside its own transaction.
        # Running total so far: 10 + 4*495 = 1,990 USDC.
        self.assertEqual(self.storage.spent_today("agent-1", "USDC"), 1990.0)

        d = engine.evaluate(self._intent(payee="0xRepeatMerchant", amount=20.0))
        self.assertEqual(d.decision, Decision.BLOCK)
        self.assertTrue(any(
            m.rule_id == "daily_cap_exceeded" and m.severity.value == "BLOCK"
            for m in d.matched_rules
        ))

    def test_daily_cap_is_atomic_for_parallel_payments(self):
        policy_path = os.path.join(self.tmpdir, "concurrent_daily_cap_policy.yaml")
        with open(policy_path, "w") as fh:
            fh.write(POLICY_YAML.replace("rate_limit_per_minute: 5", "rate_limit_per_minute: 100"))
        policy = Policy.load(policy_path)
        engine = GuardrailEngine(policy, self.storage)

        for index in range(49):
            decision = engine.evaluate(
                self._intent(
                    payee="0xRepeatMerchant",
                    amount=40.0,
                    resource=f"prefill-{index}",
                )
            )
            self.assertEqual(decision.decision, Decision.ALLOW)

        self.assertEqual(self.storage.spent_today("agent-1", "USDC"), 1960.0)
        # Use two independent SQLite connections and separate Storage locks.
        # BEGIN IMMEDIATE must serialize the read/check/write across workers.
        other_storage = Storage(self.db_path)
        other_engine = GuardrailEngine(policy, other_storage)
        barrier = threading.Barrier(2)

        def authorize_concurrently(index):
            barrier.wait(timeout=5)
            worker_engine = engine if index == 1 else other_engine
            return worker_engine.evaluate(
                self._intent(
                    payee="0xRepeatMerchant",
                    amount=40.0,
                    resource=f"parallel-{index}",
                )
            )

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                decisions = list(pool.map(authorize_concurrently, (1, 2)))
            self.assertEqual(
                sorted(decision.decision.value for decision in decisions),
                ["ALLOW", "BLOCK"],
            )
            self.assertEqual(self.storage.spent_today("agent-1", "USDC"), 2000.0)
            self.assertEqual(other_storage.spent_today("agent-1", "USDC"), 2000.0)
            self.assertEqual(sum(decision.decision == Decision.ALLOW for decision in decisions), 1)
        finally:
            other_storage.close()

    def test_warning_review_daily_cap_is_atomic_across_storage_connections(self):
        policy_path = os.path.join(self.tmpdir, "concurrent_warning_cap_policy.yaml")
        with open(policy_path, "w") as fh:
            fh.write(POLICY_YAML.replace("rate_limit_per_minute: 5", "rate_limit_per_minute: 100"))
        policy = Policy.load(policy_path)
        first_engine = GuardrailEngine(policy, self.storage)
        second_storage = Storage(self.db_path)
        second_engine = GuardrailEngine(policy, second_storage)

        for index in range(49):
            decision = first_engine.evaluate(
                self._intent(
                    payee="0xRepeatMerchant",
                    amount=40.0,
                    resource=f"warning-prefill-{index}",
                )
            )
            self.assertEqual(decision.decision, Decision.ALLOW)
        self.assertEqual(self.storage.spent_today("agent-1", "USDC"), 1960.0)

        # Keep this regression focused on the atomic policy check + audit write.
        # The actual capability/signing path has separate tests.
        first_engine._authorize_control_plane = (
            lambda action, private_key, **kwargs: {
                "issued": action.intent_id,
                "decision": kwargs["decision"].decision.value,
            }
        )
        second_engine._authorize_control_plane = (
            lambda action, private_key, **kwargs: {
                "issued": action.intent_id,
                "decision": kwargs["decision"].decision.value,
            }
        )
        advisory = [RuleMatch("manual_review", Severity.WARN, "Explicit test review")]
        barrier = threading.Barrier(2)

        def authorize_warning(engine, index):
            barrier.wait(timeout=5)
            intent = self._intent(
                payee="0xRepeatMerchant",
                amount=40.0,
                resource=f"parallel-warning-{index}",
            )
            evidence = {
                "source": "anna-app-scoped-one-time-warning-review",
                "reviewed_rule_ids": ["manual_review"],
                "confirmed_at": __import__("time").time(),
                "approval_nonce_sha256": str(index) * 64,
            }
            try:
                result = engine.authorize_with_capability_after_warning_review(
                    intent,
                    "unused-test-capability",
                    None,
                    review_evidence=evidence,
                    advisory=advisory,
                )
                return "issued", result
            except PermissionError as exc:
                return "denied", str(exc)

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(
                    lambda item: authorize_warning(item[0], item[1]),
                    ((first_engine, 1), (second_engine, 2)),
                ))
            self.assertEqual(sorted(result[0] for result in results), ["denied", "issued"])
            issued = next(result[1] for result in results if result[0] == "issued")
            denied = next(result[1] for result in results if result[0] == "denied")
            self.assertEqual(issued["decision"], "ALLOW")
            self.assertIn("fresh policy decision is BLOCK", denied)
            self.assertEqual(self.storage.spent_today("agent-1", "USDC"), 2000.0)
            self.assertEqual(second_storage.spent_today("agent-1", "USDC"), 2000.0)
        finally:
            second_storage.close()

    def test_blocks_rate_limit(self):
        for _ in range(5):
            i = self._intent(payee="0xRepeatMerchant", amount=1.0)
            d = self.engine.evaluate(i)
            self.assertEqual(d.decision, Decision.ALLOW)

        d = self.engine.evaluate(self._intent(payee="0xRepeatMerchant", amount=1.0))
        self.assertEqual(d.decision, Decision.BLOCK)
        self.assertTrue(any(m.rule_id == "rate_limit_exceeded" for m in d.matched_rules))

    def test_block_beats_warn_when_both_present(self):
        # Blocked payee AND over per-tx cap at the same time -> still BLOCK,
        # not some averaged severity.
        d = self.engine.evaluate(self._intent(payee="0xBadActor", amount=999.0))
        self.assertEqual(d.decision, Decision.BLOCK)


if __name__ == "__main__":
    unittest.main()
