"""SQLite-backed persistence: audit log, per-(agent,asset) rate limiting,
first-seen-payee tracking, and rolling daily spend. Single-process by
default — for multiple replicas, point every process at the same file on
shared storage, or swap this module for a real database. The interface is
small and easy to re-target.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

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
CREATE INDEX IF NOT EXISTS idx_audit_agent_time ON audit_log(agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_audit_payee ON audit_log(payee);
"""


class Storage:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def record(self, intent: PaymentIntent, decision: GuardrailDecision, signature: str | None) -> None:
        self._conn.execute(
            "INSERT INTO audit_log "
            "(intent_id, agent_id, payee, asset, network, amount, decision, "
            " matched_rules_json, intent_json, signature, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                intent.intent_id,
                intent.agent_id,
                intent.payee,
                intent.asset,
                intent.network,
                intent.amount,
                decision.decision.value,
                json.dumps([m.__dict__ for m in decision.matched_rules], default=str),
                json.dumps(intent.metadata),
                signature,
                time.time(),
            ),
        )
        self._conn.commit()

    def payee_seen_before(self, agent_id: str, payee: str, exclude_intent_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM audit_log WHERE agent_id = ? AND payee = ? AND intent_id != ? "
            "AND decision != 'BLOCK' LIMIT 1",
            (agent_id, payee, exclude_intent_id),
        ).fetchone()
        return row is not None

    def spent_today(self, agent_id: str, asset: str) -> float:
        since = time.time() - 24 * 3600
        row = self._conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM audit_log "
            "WHERE agent_id = ? AND asset = ? AND created_at >= ? AND decision != 'BLOCK'",
            (agent_id, asset, since),
        ).fetchone()
        return float(row[0] or 0.0)

    def calls_last_minute(self, agent_id: str) -> int:
        since = time.time() - 60
        row = self._conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE agent_id = ? AND created_at >= ?",
            (agent_id, since),
        ).fetchone()
        return int(row[0] or 0)

    def history(self, agent_id: str, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT intent_id, payee, asset, network, amount, decision, created_at "
            "FROM audit_log WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
            (agent_id, limit),
        ).fetchall()
        cols = ["intent_id", "payee", "asset", "network", "amount", "decision", "created_at"]
        return [dict(zip(cols, r)) for r in rows]

    def close(self) -> None:
        self._conn.close()
