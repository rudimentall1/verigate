"""Cross-process regression tests for atomic policy accounting.

Each worker opens an independent SQLite connection. The test proves that
GuardrailEngine's BEGIN IMMEDIATE transaction serializes the read/check/write
sequence, not merely the nonce INSERT. Two concurrent payments that each fit
the remaining daily budget must not both receive ALLOW when their combined
amount exceeds the cap.
"""

from __future__ import annotations

import multiprocessing
import tempfile
import unittest
from pathlib import Path

from core.storage import Storage


def _evaluate_daily_cap_worker(db_path, policy_path, worker_id, barrier, queue):
    """Evaluate one payment using an independent process and DB connection."""
    from core.engine import GuardrailEngine
    from core.models import PaymentIntent
    from core.policy import Policy

    storage = Storage(db_path)
    try:
        engine = GuardrailEngine(Policy.load(policy_path), storage)
        barrier.wait(timeout=30)
        intent = PaymentIntent(
            intent_id=f"concurrent-daily-cap-{worker_id}",
            agent_id="shared-agent",
            payee=f"merchant-{worker_id}",
            asset="USDC",
            network="base",
            amount=7.0,
        )
        decision = engine.evaluate(intent)
        queue.put(("OK", decision.decision.value, intent.intent_id))
    except Exception as exc:  # noqa: BLE001 - propagate worker failures to parent
        queue.put(("ERROR", repr(exc), worker_id))
    finally:
        storage.close()


class ConcurrentPolicyAccountingTest(unittest.TestCase):
    def test_parallel_payments_cannot_overspend_daily_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = str(root / "accounting.db")
            policy_path = root / "policy.yaml"
            policy_path.write_text(
                "allowed_networks: [base]\n"
                "allowed_assets: [USDC]\n"
                "daily_cap:\n"
                "  USDC: 10\n",
                encoding="utf-8",
            )

            # Create the schema before workers race to open independent
            # connections. The barrier aligns their policy evaluations.
            Storage(db_path).close()

            ctx = multiprocessing.get_context("spawn")
            queue = ctx.Queue()
            worker_count = 2
            barrier = ctx.Barrier(worker_count)
            workers = [
                ctx.Process(
                    target=_evaluate_daily_cap_worker,
                    args=(db_path, str(policy_path), worker_id, barrier, queue),
                )
                for worker_id in range(worker_count)
            ]

            try:
                for worker in workers:
                    worker.start()

                results = [queue.get(timeout=60) for _ in workers]

                for worker in workers:
                    worker.join(timeout=15)
                    self.assertFalse(worker.is_alive(), "worker process hung")
                    self.assertEqual(worker.exitcode, 0, "worker process crashed")

                errors = [result for result in results if result[0] != "OK"]
                self.assertEqual(errors, [], f"worker(s) failed: {errors}")

                decisions = [result[1] for result in results]
                self.assertCountEqual(decisions, ["ALLOW", "BLOCK"])

                # The first authorization consumes 7 of the 10 USDC budget.
                # The racing second request sees that committed state and blocks.
                audit = Storage(db_path)
                try:
                    self.assertEqual(audit.calls_last_minute("shared-agent"), 2)
                    self.assertEqual(audit.spent_today("shared-agent", "USDC"), 7.0)
                    self.assertEqual(audit.count_intent("concurrent-daily-cap-0"), 1)
                    self.assertEqual(audit.count_intent("concurrent-daily-cap-1"), 1)
                finally:
                    audit.close()
            finally:
                for worker in workers:
                    if worker.is_alive():
                        worker.terminate()
                    worker.join(timeout=5)
                queue.close()
                queue.join_thread()


if __name__ == "__main__":
    unittest.main()
