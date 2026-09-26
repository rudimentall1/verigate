import unittest

from attest.keys import generate_keypair, load_public_key
from core.authority_replay import replay_authority_decision


class AuthorityReplayTest(unittest.TestCase):
    def test_replay_verifies_intact_historical_head(self):
        from core.storage import Storage
        storage = Storage(":memory:")
        event = {"event_id": "e1", "agent_id": "a", "capability_id": "c", "event_type": "EXECUTION_CONFIRMED"}
        storage.append_authority_ledger(event)
        self.assertTrue(storage.verify_authority_ledger("a", "c")[0])

    def test_historical_head_mismatch_is_rejected(self):
        from core.storage import Storage
        storage = Storage(":memory:")
        storage.append_authority_ledger({"event_id": "e1", "agent_id": "a", "capability_id": "c", "event_type": "EXECUTION_CONFIRMED"})
        self.assertNotEqual(storage.authority_ledger_head("a", "c"), "1" * 64)

    def test_historical_replay_survives_later_authority_events(self):
        from core.storage import Storage
        from attest.keys import generate_keypair, load_public_key, load_private_key, load_public_key
        import tempfile
        from pathlib import Path

        storage = Storage(":memory:")
        from core.authority_state import DynamicAuthorityService
        service = DynamicAuthorityService(storage)
        service.record_event(
            agent_id="a", capability_id="c",
            event_type="EXECUTION_CONFIRMED", evidence_ref="e1",
        )
        head = storage.authority_ledger_head("a", "c")
        snapshot = DynamicAuthorityService(storage).snapshot("a", "c")
        storage.append_authority_ledger({
            "event_id": "e2", "agent_id": "a", "capability_id": "c",
            "event_type": "EXECUTION_CONFIRMED",
        })
        self.assertNotEqual(storage.authority_ledger_head("a", "c"), head)

        with tempfile.TemporaryDirectory() as tmp:
            private_path = Path(tmp) / "issuer.key"
            public_path = Path(tmp) / "issuer.pub"
            generate_keypair(private_path, public_path)
            private = load_private_key(private_path)
            public = load_public_key(public_path)
            from unittest.mock import patch
            auth = {"payload": {
                "agent_id": "a",
                "capability_id": "c",
                "authority_ledger_head_hash": head,
                "authority_state": snapshot.as_dict(),
                "authority_state_sha256": snapshot.digest,
                "authority_multiplier": snapshot.multiplier,
                "authority_policy_sha256": service.policy.digest,
                "authority_policy": service.policy.as_dict(),
                "evaluated_at": snapshot.evaluated_at,
                "history_start_at": snapshot.evaluated_at - service.policy.window_seconds,
            }}
            with patch("core.authority_replay.verify_execution_authorization", return_value=(True, "valid")):
                ok, reason, details = replay_authority_decision(storage, auth, public)
            self.assertTrue(ok, reason)
            self.assertEqual(details["ledger_sequence"], 1)
            self.assertEqual(details["live_ledger_sequence"], 2)
            self.assertEqual(details["ledger_head_hash"], head)

    def test_replay_uses_historically_bound_authority_policy(self):
        from core.storage import Storage
        from core.authority_state import DynamicAuthorityService, AuthorityPolicy
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        storage = Storage(":memory:")
        historical_policy = AuthorityPolicy(probation_successes=1, standard_successes=3, standard_multiplier=0.40)
        service = DynamicAuthorityService(storage, historical_policy)
        service.record_event(agent_id="a", capability_id="c", event_type="EXECUTION_CONFIRMED", evidence_ref="e1")
        snapshot = service.snapshot("a", "c")
        head = snapshot.ledger_head_hash
        with tempfile.TemporaryDirectory() as tmp:
            private_path = Path(tmp) / "issuer.key"
            public_path = Path(tmp) / "issuer.pub"
            generate_keypair(private_path, public_path)
            public = load_public_key(public_path)
            auth = {"payload": {
                "agent_id": "a",
                "capability_id": "c",
                "authority_ledger_head_hash": head,
                "authority_state": snapshot.as_dict(),
                "authority_state_sha256": snapshot.digest,
                "authority_multiplier": snapshot.multiplier,
                "authority_policy_sha256": historical_policy.digest,
                "authority_policy": historical_policy.as_dict(),
                "evaluated_at": snapshot.evaluated_at,
                "history_start_at": snapshot.evaluated_at - historical_policy.window_seconds,
            }}
            with patch("core.authority_replay.verify_execution_authorization", return_value=(True, "valid")):
                ok, reason, details = replay_authority_decision(storage, auth, public)
            self.assertTrue(ok, reason)
            self.assertEqual(details["authority_multiplier"], 0.40)

    def test_replay_respects_historical_policy_window(self):
        from core.storage import Storage
        from core.authority_state import DynamicAuthorityService, AuthorityPolicy
        import time
        storage = Storage(":memory:")
        policy = AuthorityPolicy(window_seconds=100, probation_successes=1)
        service = DynamicAuthorityService(storage, policy)
        service.record_event(agent_id="a", capability_id="c", event_type="EXECUTION_CONFIRMED", evidence_ref="old", occurred_at=100.0)
        service.record_event(agent_id="a", capability_id="c", event_type="EXECUTION_FAILED", evidence_ref="recent", occurred_at=950.0)
        snapshot = service.snapshot("a", "c", now=1000.0)
        self.assertEqual(snapshot.successes, 0)
        self.assertEqual(snapshot.adverse_events, 1)
        self.assertEqual(snapshot.history_start_at, 900.0)
        self.assertEqual(snapshot.evaluated_at, 1000.0)

    def test_replay_ignores_reset_issued_after_historical_snapshot(self):
        from core.storage import Storage
        from core.authority_state import DynamicAuthorityService, AuthorityPolicy
        from unittest.mock import patch

        storage = Storage(":memory:")
        policy = AuthorityPolicy(window_seconds=100)
        service = DynamicAuthorityService(storage, policy)
        service.record_event(
            agent_id="a", capability_id="c",
            event_type="EXECUTION_CONFIRMED", evidence_ref="historical-success",
            occurred_at=950.0,
        )
        snapshot = service.snapshot("a", "c", now=1000.0)
        head = snapshot.ledger_head_hash

        storage.register_authority_reset({
            "payload": {
                "reset_id": "reset-later", "agent_id": "a", "capability_id": "c",
                "governor_id": "governor", "epoch": 1,
                "reason": "later incident review", "issued_at": 2000.0,
                "nonce": "nonce-later",
            },
            "signature": "not-used-by-replay",
        })

        auth = {"payload": {
            "agent_id": "a",
            "capability_id": "c",
            "authority_ledger_head_hash": head,
            "authority_state": snapshot.as_dict(),
            "authority_state_sha256": snapshot.digest,
            "authority_multiplier": snapshot.multiplier,
            "authority_policy_sha256": policy.digest,
            "authority_policy": policy.as_dict(),
            "evaluated_at": snapshot.evaluated_at,
            "history_start_at": snapshot.history_start_at,
        }}
        with patch("core.authority_replay.verify_execution_authorization", return_value=(True, "valid")):
            ok, reason, details = replay_authority_decision(storage, auth, object())
        self.assertTrue(ok, reason)
        self.assertEqual(details["authority_state"]["history_start_at"], 900.0)
        self.assertEqual(details["authority_state"]["successes"], 1)

    def test_ledger_tamper_is_rejected(self):
        from core.storage import Storage
        storage = Storage(":memory:")
        storage.append_authority_ledger({"event_id": "e1", "agent_id": "a", "capability_id": "c", "event_type": "EXECUTION_CONFIRMED"})
        storage._conn.execute("UPDATE authority_ledger SET event_json = ? WHERE event_id = ?", ('{"event_type":"TAMPERED"}', 'e1'))
        storage._conn.commit()
        self.assertFalse(storage.verify_authority_ledger("a", "c")[0])


if __name__ == "__main__":
    unittest.main()
