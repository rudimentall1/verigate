import unittest

from attest.keys import generate_keypair
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
        from attest.keys import generate_keypair, load_private_key, load_public_key
        import tempfile
        from pathlib import Path

        storage = Storage(":memory:")
        storage.append_authority_ledger({
            "event_id": "e1", "agent_id": "a", "capability_id": "c",
            "event_type": "EXECUTION_CONFIRMED",
        })
        head = storage.authority_ledger_head("a", "c")
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
            }}
            with patch("core.authority_replay.verify_execution_authorization", return_value=(True, "valid")):
                ok, reason, details = replay_authority_decision(storage, auth, public)
            self.assertTrue(ok, reason)
            self.assertEqual(details["ledger_sequence"], 1)
            self.assertEqual(details["live_ledger_sequence"], 2)
            self.assertEqual(details["ledger_head_hash"], head)

    def test_ledger_tamper_is_rejected(self):
        from core.storage import Storage
        storage = Storage(":memory:")
        storage.append_authority_ledger({"event_id": "e1", "agent_id": "a", "capability_id": "c", "event_type": "EXECUTION_CONFIRMED"})
        storage._conn.execute("UPDATE authority_ledger SET event_json = ? WHERE event_id = ?", ('{"event_type":"TAMPERED"}', 'e1'))
        storage._conn.commit()
        self.assertFalse(storage.verify_authority_ledger("a", "c")[0])


if __name__ == "__main__":
    unittest.main()
