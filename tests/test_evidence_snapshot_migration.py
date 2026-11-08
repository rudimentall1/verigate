"""Regression tests for immutable Evidence Graph snapshot history and schema migration."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.storage import Storage


class EvidenceSnapshotMigrationTest(unittest.TestCase):
    def test_legacy_unique_digest_index_is_removed_without_losing_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.db"
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE evidence_graph_snapshots ("
                "snapshot_id TEXT PRIMARY KEY, "
                "authorization_id TEXT NOT NULL, "
                "graph_sha256 TEXT NOT NULL UNIQUE, "
                "graph_version INTEGER NOT NULL, "
                "graph_json TEXT NOT NULL, "
                "created_at REAL NOT NULL)"
            )
            conn.execute(
                "CREATE INDEX idx_evidence_graph_snapshots_authorization "
                "ON evidence_graph_snapshots(authorization_id, created_at)"
            )
            conn.execute(
                "INSERT INTO evidence_graph_snapshots VALUES (?, ?, ?, ?, ?, ?)",
                ("legacy-1", "auth-1", "a" * 64, 1, '{"authorization_id":"auth-1"}', 1.0),
            )
            conn.commit()
            conn.close()

            storage = Storage(db_path)
            try:
                existing = storage.evidence_graph_snapshot("legacy-1")
                self.assertIsNotNone(existing)
                self.assertEqual(existing["graph_sha256"], "a" * 64)

                first = {
                    "snapshot_id": "snapshot-2",
                    "authorization_id": "auth-1",
                    "graph_sha256": "b" * 64,
                    "graph": {"authorization_id": "auth-1", "snapshot_at": 2},
                }
                second = {
                    "snapshot_id": "snapshot-3",
                    "authorization_id": "auth-1",
                    "graph_sha256": "b" * 64,
                    "graph": {"authorization_id": "auth-1", "snapshot_at": 2},
                }
                storage.record_evidence_graph_snapshot(first)
                storage.record_evidence_graph_snapshot(second)

                history = storage.evidence_graph_snapshots("auth-1", limit=10)
                self.assertEqual(len(history), 3)
                self.assertEqual(
                    {item["snapshot_id"] for item in history},
                    {"legacy-1", "snapshot-2", "snapshot-3"},
                )
            finally:
                storage.close()

    def test_failed_migration_rolls_back_table_rename_and_preserves_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy-rollback.db"
            seed = sqlite3.connect(db_path)
            seed.execute(
                "CREATE TABLE evidence_graph_snapshots ("
                "snapshot_id TEXT PRIMARY KEY, "
                "authorization_id TEXT NOT NULL, "
                "graph_sha256 TEXT NOT NULL UNIQUE, "
                "graph_version INTEGER NOT NULL, "
                "graph_json TEXT NOT NULL, "
                "created_at REAL NOT NULL)"
            )
            seed.execute(
                "INSERT INTO evidence_graph_snapshots VALUES (?, ?, ?, ?, ?, ?)",
                ("kept", "auth-rollback", "c" * 64, 1, '{"authorization_id":"auth-rollback"}', 1.0),
            )
            seed.commit()
            seed.close()

            real_connect = sqlite3.connect
            opened = []

            def deny_replacement_table(*args, **kwargs):
                connection = real_connect(*args, **kwargs)

                def authorizer(action, arg1, arg2, database, trigger):
                    if action == sqlite3.SQLITE_CREATE_TABLE and arg1 == "evidence_graph_snapshots":
                        return sqlite3.SQLITE_DENY
                    return sqlite3.SQLITE_OK

                connection.set_authorizer(authorizer)
                opened.append(connection)
                return connection

            try:
                with patch("core.storage.sqlite3.connect", side_effect=deny_replacement_table):
                    with self.assertRaises(sqlite3.DatabaseError):
                        Storage(db_path)

                reopened = real_connect(db_path)
                try:
                    tables = {
                        row[0] for row in reopened.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        ).fetchall()
                    }
                    self.assertIn("evidence_graph_snapshots", tables)
                    self.assertNotIn("evidence_graph_snapshots_legacy", tables)
                    row = reopened.execute(
                        "SELECT snapshot_id, graph_sha256 FROM evidence_graph_snapshots"
                    ).fetchone()
                    self.assertEqual(row, ("kept", "c" * 64))
                    unique_indexes = [
                        index for index in reopened.execute(
                            "PRAGMA index_list(evidence_graph_snapshots)"
                        ).fetchall() if index[2]
                    ]
                    self.assertTrue(unique_indexes, "old UNIQUE digest constraint should remain after rollback")
                finally:
                    reopened.close()
            finally:
                for connection in opened:
                    connection.close()


if __name__ == "__main__":
    unittest.main()