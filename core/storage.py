"""SQLite-backed persistence for VeriGate.

Provides:
- audit logging;
- per-agent rate limiting;
- first-seen-payee tracking;
- rolling 24-hour spend accounting;
- transaction support for atomic decision + accounting.

The transaction API uses BEGIN IMMEDIATE so decision state reads and the
resulting audit record can be committed or rolled back as one unit.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .models import GuardrailDecision, PaymentIntent


_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intent_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    payee TEXT NOT NULL,
    asset TEXT NOT NULL,
    network TEXT NOT NULL,
    amount REAL NOT NULL,
    decision TEXT NOT NULL,
    matched_rules_json TEXT NOT NULL,
    intent_json TEXT NOT NULL,
    signature TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_agent_time
    ON audit_log(agent_id, created_at);

CREATE INDEX IF NOT EXISTS idx_audit_agent_payee
    ON audit_log(agent_id, payee);

CREATE INDEX IF NOT EXISTS idx_audit_payee
    ON audit_log(payee);

CREATE TABLE IF NOT EXISTS execution_nonces (
    nonce TEXT PRIMARY KEY,
    authorization_id TEXT NOT NULL,
    intent_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    consumed_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_receipts (
    receipt_id TEXT PRIMARY KEY,
    authorization_id TEXT NOT NULL UNIQUE,
    intent_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    network TEXT NOT NULL,
    status TEXT NOT NULL,
    transaction_ref TEXT,
    receipt_json TEXT NOT NULL,
    signature TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_execution_receipts_intent
    ON execution_receipts(intent_id);

CREATE INDEX IF NOT EXISTS idx_execution_receipts_agent_time
    ON execution_receipts(agent_id, created_at);
"""


class Storage:
    """SQLite persistence with process-local synchronization."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)

        parent = Path(self.db_path).parent
        parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=30.0,
        )

        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a group of storage operations atomically."""
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def record(
        self,
        intent: PaymentIntent,
        decision: GuardrailDecision,
        signature: str | None,
        *,
        commit: bool = True,
    ) -> None:
        """Record one payment attempt.

        commit=False is used when the caller already owns a transaction.
        """
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit_log "
                "(intent_id, agent_id, payee, asset, network, amount, decision, "
                "matched_rules_json, intent_json, signature, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    intent.intent_id,
                    intent.agent_id,
                    intent.payee,
                    intent.asset,
                    intent.network,
                    intent.amount,
                    decision.decision.value,
                    json.dumps(
                        [
                            {
                                "rule_id": m.rule_id,
                                "severity": m.severity.value,
                                "message": m.message,
                            }
                            for m in decision.matched_rules
                        ],
                        separators=(",", ":"),
                    ),
                    json.dumps(intent.metadata, separators=(",", ":")),
                    signature,
                    time.time(),
                ),
            )

            if commit:
                self._conn.commit()

    def payee_seen_before(
        self,
        agent_id: str,
        payee: str,
        exclude_intent_id: str,
    ) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 "
                "FROM audit_log "
                "WHERE agent_id = ? "
                "AND payee = ? "
                "AND intent_id != ? "
                "AND decision != 'BLOCK' "
                "LIMIT 1",
                (agent_id, payee, exclude_intent_id),
            ).fetchone()

            return row is not None

    def spent_today(self, agent_id: str, asset: str) -> float:
        """Return spend in the rolling 24-hour window.

        BLOCK decisions are excluded from spend accounting.
        """
        since = time.time() - 24 * 3600

        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(amount), 0) "
                "FROM audit_log "
                "WHERE agent_id = ? "
                "AND asset = ? "
                "AND created_at >= ? "
                "AND decision != 'BLOCK'",
                (agent_id, asset, since),
            ).fetchone()

            return float(row[0] or 0.0)

    def calls_last_minute(self, agent_id: str) -> int:
        """Return all recorded payment attempts in the last 60 seconds."""
        since = time.time() - 60

        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) "
                "FROM audit_log "
                "WHERE agent_id = ? "
                "AND created_at >= ?",
                (agent_id, since),
            ).fetchone()

            return int(row[0] or 0)

    def history(self, agent_id: str, limit: int = 50) -> list[dict]:
        if limit < 1:
            return []

        with self._lock:
            rows = self._conn.execute(
                "SELECT intent_id, payee, asset, network, amount, "
                "decision, created_at "
                "FROM audit_log "
                "WHERE agent_id = ? "
                "ORDER BY created_at DESC "
                "LIMIT ?",
                (agent_id, limit),
            ).fetchall()

        columns = [
            "intent_id",
            "payee",
            "asset",
            "network",
            "amount",
            "decision",
            "created_at",
        ]

        return [dict(zip(columns, row)) for row in rows]


    def count_intent(self, intent_id: str) -> int:
        """Return the number of audit rows for one intent ID."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE intent_id = ?",
                (intent_id,),
            ).fetchone()

            return int(row[0] or 0)

    def consume_execution_nonce(
        self,
        nonce: str,
        authorization_id: str,
        intent_id: str,
        agent_id: str,
    ) -> bool:
        """Atomically consume a nonce; return False when it was already used."""
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO execution_nonces "
                    "(nonce, authorization_id, intent_id, agent_id, consumed_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (nonce, authorization_id, intent_id, agent_id, time.time()),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                self._conn.rollback()
                return False

    def record_execution_receipt(self, receipt: dict) -> None:
        payload = receipt["payload"]
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO execution_receipts "
                    "(receipt_id, authorization_id, intent_id, agent_id, network, status, "
                    "transaction_ref, receipt_json, signature, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        payload["receipt_id"],
                        payload["authorization_id"],
                        payload["intent_id"],
                        payload["agent_id"],
                        payload.get("network") or "",
                        payload["status"],
                        payload.get("transaction_ref"),
                        json.dumps(receipt, sort_keys=True, separators=(",", ":")),
                        receipt["signature"],
                        time.time(),
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                self._conn.rollback()
                raise ValueError("execution receipt already recorded") from exc

    def update_execution_receipt(self, receipt: dict) -> None:
        payload = receipt["payload"]
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE execution_receipts SET status = ?, transaction_ref = ?, "
                "receipt_json = ?, signature = ?, created_at = ? "
                "WHERE authorization_id = ?",
                (
                    payload["status"],
                    payload.get("transaction_ref"),
                    json.dumps(receipt, sort_keys=True, separators=(",", ":")),
                    receipt["signature"],
                    time.time(),
                    payload["authorization_id"],
                ),
            )
            if cursor.rowcount != 1:
                self._conn.rollback()
                raise ValueError("execution receipt not found")
            self._conn.commit()

    def execution_receipt_by_authorization(self, authorization_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT receipt_json FROM execution_receipts WHERE authorization_id = ?",
                (authorization_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def execution_receipts(self, agent_id: str, limit: int = 50) -> list[dict]:
        if limit < 1:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT receipt_json FROM execution_receipts "
                "WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]


    def update_signature(self, intent_id: str, signature: str) -> None:
        """Attach a signature to an existing audit row.

        Refuses to silently create/update a row that does not exist.
        """
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE audit_log SET signature = ? WHERE intent_id = ? AND signature IS NULL",
                (signature, intent_id),
            )

            if cursor.rowcount != 1:
                self._conn.rollback()
                raise ValueError(
                    f"intent_id '{intent_id}' was not found"
                )

            self._conn.commit()

    def set_signature(self, intent_id: str, signature: str) -> None:
        """Backward-compatible alias for update_signature()."""
        self.update_signature(intent_id, signature)

    def close(self) -> None:
        with self._lock:
            self._conn.close()
