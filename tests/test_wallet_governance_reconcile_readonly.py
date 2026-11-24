import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.wallet_governance_log_reconcile import load_local_history_read_only


class WalletGovernanceReconcileReadOnlyDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_database_is_not_created(self):
        database = self.root / "missing.db"

        with self.assertRaises(sqlite3.OperationalError):
            load_local_history_read_only(database, "anna-installation:" + "1" * 64)

        self.assertFalse(database.exists())

    def test_reads_local_history_without_changing_database(self):
        database = self.root / "verigate.db"
        principal = "anna-installation:" + "2" * 64
        envelope = {
            "action": {
                "action_id": "action-read-only-001",
                "action": "WALLET_ENROLL",
                "installation_principal": principal,
                "enrollment_id": "enrollment-read-only-001",
            }
        }
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE wallet_enrollment_governance_actions ("
                "action_id TEXT PRIMARY KEY, "
                "installation_principal TEXT NOT NULL, "
                "envelope_json TEXT NOT NULL, "
                "created_at REAL NOT NULL)"
            )
            connection.execute(
                "INSERT INTO wallet_enrollment_governance_actions "
                "(action_id, installation_principal, envelope_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                ("action-read-only-001", principal, json.dumps(envelope), 1.0),
            )
            connection.commit()
            schema_version_before = connection.execute("PRAGMA schema_version").fetchone()[0]
            row_count_before = connection.execute(
                "SELECT COUNT(*) FROM wallet_enrollment_governance_actions"
            ).fetchone()[0]

        history = load_local_history_read_only(database, principal)

        self.assertEqual(history, [envelope])
        with sqlite3.connect(database) as connection:
            self.assertEqual(
                connection.execute("PRAGMA schema_version").fetchone()[0],
                schema_version_before,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM wallet_enrollment_governance_actions"
                ).fetchone()[0],
                row_count_before,
            )

    def test_loader_connection_rejects_database_writes(self):
        database = self.root / "verigate.db"
        principal = "anna-installation:" + "3" * 64
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE wallet_enrollment_governance_actions ("
                "action_id TEXT PRIMARY KEY, "
                "installation_principal TEXT NOT NULL, "
                "envelope_json TEXT NOT NULL, "
                "created_at REAL NOT NULL)"
            )
            connection.commit()

        real_connect = sqlite3.connect
        write_was_rejected = []

        class ProbedConnection:
            def __init__(self, connection):
                self.connection = connection

            def execute(self, sql, parameters=()):
                if sql.startswith("SELECT") and not write_was_rejected:
                    with self_case.assertRaises(sqlite3.OperationalError):
                        self.connection.execute(
                            "INSERT INTO wallet_enrollment_governance_actions "
                            "(action_id, installation_principal, envelope_json, created_at) "
                            "VALUES ('write-probe', ?, '{}', 1)",
                            (principal,),
                        )
                    write_was_rejected.append(True)
                return self.connection.execute(sql, parameters)

            def close(self):
                self.connection.close()

        self_case = self

        def connect_and_probe(*args, **kwargs):
            return ProbedConnection(real_connect(*args, **kwargs))

        with patch(
            "scripts.wallet_governance_log_reconcile.sqlite3.connect",
            side_effect=connect_and_probe,
        ):
            history = load_local_history_read_only(database, principal)

        self.assertEqual(history, [])
        self.assertEqual(write_was_rejected, [True])


if __name__ == "__main__":
    unittest.main()
