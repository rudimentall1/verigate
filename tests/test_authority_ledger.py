import tempfile
import unittest
from pathlib import Path
from core.storage import Storage
from core.authority_state import DynamicAuthorityService

class AuthorityLedgerTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.storage=Storage(Path(self.tmp.name)/"v.db")
        self.service=DynamicAuthorityService(self.storage)
    def tearDown(self): self.storage.close(); self.tmp.cleanup()
    def test_events_form_hash_chain(self):
        a=self.service.record_event(agent_id="a", capability_id="c", event_type="EXECUTION_CONFIRMED", evidence_ref="r1")
        b=self.service.record_event(agent_id="a", capability_id="c", event_type="EXECUTION_CONFIRMED", evidence_ref="r2")
        self.assertEqual(a["ledger"]["sequence"],1); self.assertEqual(b["ledger"]["sequence"],2)
        self.assertEqual(b["ledger"]["prev_event_hash"],a["ledger"]["event_hash"])
        self.assertEqual(self.storage.verify_authority_ledger("a","c"),(True,"valid"))
    def test_duplicate_event_is_idempotent(self):
        a=self.service.record_event(agent_id="a", capability_id="c", event_type="EXECUTION_CONFIRMED", evidence_ref="r1")
        b=self.service.record_event(agent_id="a", capability_id="c", event_type="EXECUTION_CONFIRMED", evidence_ref="r1")
        self.assertEqual(a["ledger"]["event_hash"],b["ledger"]["event_hash"]); self.assertEqual(len(self.storage.authority_ledger("a","c")),1)
    def test_tamper_is_detected(self):
        self.service.record_event(agent_id="a", capability_id="c", event_type="EXECUTION_CONFIRMED", evidence_ref="r1")
        with self.storage._lock:
            self.storage._conn.execute("UPDATE authority_ledger SET event_json = ? WHERE sequence = 1", ('{"tampered":true}',)); self.storage._conn.commit()
        self.assertEqual(self.storage.verify_authority_ledger("a","c"),(False,"authority ledger event digest mismatch"))

if __name__ == "__main__": unittest.main()
