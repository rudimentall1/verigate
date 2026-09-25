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

    def test_ledger_tamper_is_rejected(self):
        from core.storage import Storage
        storage = Storage(":memory:")
        storage.append_authority_ledger({"event_id": "e1", "agent_id": "a", "capability_id": "c", "event_type": "EXECUTION_CONFIRMED"})
        storage._conn.execute("UPDATE authority_ledger SET event_json = ? WHERE event_id = ?", ('{"event_type":"TAMPERED"}', 'e1'))
        storage._conn.commit()
        self.assertFalse(storage.verify_authority_ledger("a", "c")[0])


if __name__ == "__main__":
    unittest.main()
