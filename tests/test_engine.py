import os
import tempfile
import unittest

from core.engine import GuardrailEngine
from core.models import Decision, PaymentIntent
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
        self.storage = Storage(os.path.join(self.tmpdir, "audit.db"))
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
        self.storage.record(first, d1, signature=None)

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

    def test_warns_over_daily_cap(self):
        # Daily-cap accumulation needs several prior payments, each under
        # per_tx_cap (500) to avoid being BLOCKed (and thus excluded from
        # the running total), without tripping the separate rate-limit
        # rule — so this test uses its own policy with a generous rate
        # limit, isolating the one rule under test.
        policy_path = os.path.join(self.tmpdir, "daily_cap_policy.yaml")
        with open(policy_path, "w") as fh:
            fh.write(POLICY_YAML.replace("rate_limit_per_minute: 5", "rate_limit_per_minute: 50"))
        policy = Policy.load(policy_path)
        engine = GuardrailEngine(policy, self.storage)

        established = self._intent(payee="0xRepeatMerchant", amount=10.0)
        d0 = engine.evaluate(established)
        self.storage.record(established, d0, signature=None)

        for _ in range(4):
            top_up = self._intent(payee="0xRepeatMerchant", amount=495.0)
            d = engine.evaluate(top_up)
            self.storage.record(top_up, d, signature=None)
        # running total so far: 10 + 4*495 = 1990

        d = engine.evaluate(self._intent(payee="0xRepeatMerchant", amount=20.0))
        self.assertEqual(d.decision, Decision.WARN)
        self.assertTrue(any(m.rule_id == "daily_cap_exceeded" for m in d.matched_rules))

    def test_blocks_rate_limit(self):
        for _ in range(5):
            i = self._intent(payee="0xRepeatMerchant", amount=1.0)
            d = self.engine.evaluate(i)
            self.storage.record(i, d, signature=None)

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
