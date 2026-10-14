"""Regression tests for exact ActionIntent amounts at the SQLite boundary."""

from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from core.models import ActionIntent, Decision, GuardrailDecision
from core.storage import Storage


class ActionIntentDecimalStorageTest(unittest.TestCase):
    def test_decimal_amount_is_stored_and_exact_value_remains_in_audit_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = Storage(Path(temp_dir) / "actions.db")
            try:
                intent = ActionIntent(
                    agent_id="portaldot-local-demo-agent",
                    action_type="portaldot.native_transfer",
                    target="0x1111111111111111111111111111111111111111",
                    amount=Decimal("1000000"),
                    amount_exact="1000000",
                    asset="tPOTv3",
                    network="portaldot-v3",
                    intent_id="decimal-storage-regression",
                )
                decision = GuardrailDecision(
                    intent_id=intent.intent_id,
                    agent_id=intent.agent_id,
                    decision=Decision.ALLOW,
                    matched_rules=(),
                )

                storage.record_action(intent, decision)

                row = storage._conn.execute(
                    "SELECT network, amount, intent_json FROM audit_log WHERE intent_id = ?",
                    (intent.intent_id,),
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(row[0], "portaldot-v3")
                self.assertEqual(row[1], 1000000.0)
                audit_intent = json.loads(row[2])
                self.assertEqual(audit_intent["amount"], "1000000")
                self.assertEqual(audit_intent["amount_exact"], "1000000")
            finally:
                storage.close()


if __name__ == "__main__":
    unittest.main()
