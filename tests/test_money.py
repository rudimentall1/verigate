import shutil
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from core import rules as R
from core.models import PaymentIntent
from core.money import exceeds, is_valid_amount, total
from core.policy import Policy
from core.storage import Storage


def intent(amount, asset="USDC"):
    return PaymentIntent(agent_id="a1", payee="p", asset=asset, network="base", amount=amount)


class MoneyTest(unittest.TestCase):
    def setUp(self):
        self.policy = Policy.load("policies/default.yaml")

    def test_float_drift_no_longer_decides_caps(self):
        self.assertTrue(0.1 + 0.2 > 0.3)            # the float trap
        self.assertEqual(total(0.1, 0.2), Decimal("0.3"))
        self.policy.daily_cap["USDC"] = 0.3
        # 0.1 already spent + 0.2 new == exactly 0.3: at the cap, not over it
        self.assertIsNone(R.check_daily_cap(intent(0.2), self.policy, 0.1))
        # one cent over is over
        self.assertIsNotNone(R.check_daily_cap(intent(0.21), self.policy, 0.1))

    def test_invalid_amounts_fail_closed(self):
        for bad in (float("nan"), float("inf"), float("-inf"), -5.0, True, "5", None):
            self.assertFalse(is_valid_amount(bad), bad)
            self.assertTrue(exceeds(bad, 500), bad)
        for bad in (float("nan"), -5.0):
            match = R.check_per_tx_cap(intent(bad), self.policy)
            self.assertEqual(match.rule_id, "invalid_amount")
            self.assertEqual(match.severity.value, "BLOCK")

    def test_zero_and_normal_amounts_still_valid(self):
        self.assertTrue(is_valid_amount(0))
        self.assertIsNone(R.check_per_tx_cap(intent(10.0), self.policy))
        self.assertIsNotNone(R.check_per_tx_cap(intent(500.01), self.policy))
        self.assertIsNone(R.check_per_tx_cap(intent(500.0), self.policy))

    def test_rolling_spend_sums_exactly(self):
        # mkdtemp + ignore_errors instead of TemporaryDirectory's own
        # cleanup: on Windows, SQLite's WAL sidecar files can still be
        # briefly held right after close(), which turns a passing test
        # into a spurious teardown error unrelated to what it's testing.
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        store = Storage(str(Path(tmp) / "t.db"))
        self.addCleanup(store.close)
        for n in range(10):
            store._conn.execute(
                "INSERT INTO audit_log (intent_id, agent_id, payee, asset, network, amount, "
                "decision, matched_rules_json, intent_json, signature, created_at) "
                "VALUES (?, 'a1', 'p', 'USDC', 'base', 0.1, 'ALLOW', '[]', '{}', NULL, "
                "strftime('%s','now'))",
                (f"i{n}",),
            )
        store._conn.commit()
        self.assertEqual(store.spent_today("a1", "USDC"), 1.0)


if __name__ == "__main__":
    unittest.main()
