"""core.storage.Storage is documented as providing "process-local
synchronization" -- its threading.RLock only serializes threads inside one
Python process. The only thing that can actually prevent a double-spend
across independent processes (multiple uvicorn workers, multiple replicas,
anything that isn't literally the same Python object) is SQLite's own
locking plus the UNIQUE constraint on execution_nonces.nonce.

This test is deliberately NOT threading-based: real OS processes, each
opening its own connection to the same database file, racing to consume
the exact same nonce. That's the scenario every "does this survive
multiple workers" question is actually asking about.
"""
import multiprocessing
import tempfile
import unittest
from pathlib import Path

from core.storage import Storage


def _consume_worker(db_path, nonce, authorization_id, intent_id, agent_id, queue):
    store = Storage(db_path)
    try:
        queue.put(store.consume_execution_nonce(nonce, authorization_id, intent_id, agent_id))
    except Exception as exc:  # noqa: BLE001 - surface any worker-side error to the parent
        queue.put(("ERROR", repr(exc)))
    finally:
        store.close()


class ConcurrentNonceConsumptionTest(unittest.TestCase):
    def test_only_one_process_wins_a_racing_nonce(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "concurrent.db")
            Storage(db_path).close()  # create the schema once, before racing

            n_workers = 20
            nonce = "race-nonce-1"
            ctx = multiprocessing.get_context("spawn")
            queue = ctx.Queue()
            procs = [
                ctx.Process(
                    target=_consume_worker,
                    args=(db_path, nonce, "auth-1", "intent-1", "agent-1", queue),
                )
                for _ in range(n_workers)
            ]
            for p in procs:
                p.start()
            results = [queue.get(timeout=30) for _ in range(n_workers)]
            for p in procs:
                p.join(timeout=10)
                self.assertFalse(p.is_alive(), "worker process hung")
                self.assertEqual(p.exitcode, 0, "worker process crashed")

            errors = [r for r in results if isinstance(r, tuple)]
            self.assertEqual(errors, [], f"worker(s) raised: {errors}")
            self.assertEqual(results.count(True), 1, "exactly one process must win the race")
            self.assertEqual(results.count(False), n_workers - 1)

            check = Storage(db_path)
            row = check._conn.execute(
                "SELECT COUNT(*) FROM execution_nonces WHERE nonce = ?", (nonce,)
            ).fetchone()
            check.close()
            self.assertEqual(row[0], 1, "exactly one row must be persisted for the nonce")

    def test_distinct_nonces_all_succeed_under_concurrency(self):
        # Sanity check in the other direction: genuine concurrency across
        # DIFFERENT nonces must not false-positive block each other.
        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "concurrent2.db")
            Storage(db_path).close()

            n_workers = 15
            ctx = multiprocessing.get_context("spawn")
            queue = ctx.Queue()
            procs = [
                ctx.Process(
                    target=_consume_worker,
                    args=(db_path, f"distinct-nonce-{i}", "auth-1", "intent-1", "agent-1", queue),
                )
                for i in range(n_workers)
            ]
            for p in procs:
                p.start()
            results = [queue.get(timeout=30) for _ in range(n_workers)]
            for p in procs:
                p.join(timeout=10)
                self.assertEqual(p.exitcode, 0)

            self.assertEqual(results.count(True), n_workers)


if __name__ == "__main__":
    unittest.main()
