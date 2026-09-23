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

import hashlib
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .models import ActionIntent, Capability, GuardrailDecision, PaymentIntent


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

CREATE TABLE IF NOT EXISTS authorization_artifacts (
    authorization_id TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL UNIQUE,
    agent_id TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    execution_authorization_json TEXT,
    agent_signature TEXT,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_authorization_artifacts_agent_time
    ON authorization_artifacts(agent_id, created_at);

CREATE TABLE IF NOT EXISTS capabilities (
    capability_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    capability_json TEXT NOT NULL,
    capability_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    issued_at REAL NOT NULL,
    expires_at REAL,
    revoked_at REAL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_capabilities_agent_status
    ON capabilities(agent_id, status);

CREATE TABLE IF NOT EXISTS identities (
    identity_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    identity_json TEXT NOT NULL,
    identity_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    issued_at REAL NOT NULL,
    expires_at REAL,
    revoked_at REAL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_identities_agent_status
    ON identities(agent_id, status);

CREATE TABLE IF NOT EXISTS authority_edges (
    edge_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    revoked_at REAL,
    UNIQUE(source_type, source_id, relation, target_type, target_id)
);

CREATE INDEX IF NOT EXISTS idx_authority_edges_source
    ON authority_edges(source_type, source_id, status);

CREATE INDEX IF NOT EXISTS idx_authority_edges_target
    ON authority_edges(target_type, target_id, status);

CREATE TABLE IF NOT EXISTS authority_events (
    event_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    identity_id TEXT,
    event_type TEXT NOT NULL,
    action_type TEXT,
    evidence_ref TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    occurred_at REAL NOT NULL,
    UNIQUE(agent_id, capability_id, event_type, evidence_ref)
);

CREATE INDEX IF NOT EXISTS idx_authority_events_scope_time
    ON authority_events(agent_id, capability_id, occurred_at);

CREATE TABLE IF NOT EXISTS authority_states (
    agent_id TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    state TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY(agent_id, capability_id)
);

CREATE TABLE IF NOT EXISTS policy_versions (
    policy_sha256 TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    source_ref TEXT NOT NULL,
    signed_policy_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_policy_versions_identity
    ON policy_versions(policy_id, version);

CREATE TABLE IF NOT EXISTS governed_policy_changes (
    policy_sha256 TEXT PRIMARY KEY,
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    parent_sha256 TEXT,
    action_id TEXT NOT NULL UNIQUE,
    action_nonce TEXT NOT NULL UNIQUE,
    governance_policy_sha256 TEXT NOT NULL,
    envelope_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_governed_policy_changes_identity
    ON governed_policy_changes(policy_id, version);

CREATE TABLE IF NOT EXISTS policy_controls (
    policy_id TEXT PRIMARY KEY,
    active_policy_sha256 TEXT NOT NULL,
    frozen INTEGER NOT NULL,
    control_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS policy_control_actions (
    action_id TEXT PRIMARY KEY,
    action_nonce TEXT NOT NULL UNIQUE,
    policy_id TEXT NOT NULL,
    action TEXT NOT NULL,
    envelope_json TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_policy_control_actions_policy
    ON policy_control_actions(policy_id, created_at);

CREATE TABLE IF NOT EXISTS authority_resets (
    reset_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    capability_id TEXT NOT NULL,
    governor_id TEXT NOT NULL,
    epoch INTEGER NOT NULL,
    reason TEXT NOT NULL,
    issued_at REAL NOT NULL,
    nonce TEXT NOT NULL UNIQUE,
    signed_reset_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(agent_id, capability_id, epoch)
);

CREATE TABLE IF NOT EXISTS governance_approvals (
    approval_id TEXT PRIMARY KEY,
    action_digest TEXT NOT NULL,
    governor_id TEXT NOT NULL,
    role TEXT NOT NULL,
    issued_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    nonce TEXT NOT NULL UNIQUE,
    signed_approval_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    UNIQUE(action_digest, governor_id)
);

CREATE INDEX IF NOT EXISTS idx_governance_approvals_action
    ON governance_approvals(action_digest, governor_id);

CREATE INDEX IF NOT EXISTS idx_authority_resets_scope
    ON authority_resets(agent_id, capability_id, epoch);
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
        columns = {
            row[1] for row in self._conn.execute("PRAGMA table_info(authorization_artifacts)")
        }
        if "agent_signature" not in columns:
            self._conn.execute(
                "ALTER TABLE authorization_artifacts ADD COLUMN agent_signature TEXT"
            )
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

    def record_action(
        self,
        intent: ActionIntent,
        decision: GuardrailDecision,
        signature: str | None = None,
        *,
        commit: bool = True,
    ) -> None:
        """Record a protocol-agnostic action using the legacy audit table."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO audit_log "
                "(intent_id, agent_id, payee, asset, network, amount, decision, "
                "matched_rules_json, intent_json, signature, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    intent.intent_id,
                    intent.agent_id,
                    intent.target,
                    intent.asset or "",
                    intent.network or "",
                    intent.amount if intent.amount is not None else 0.0,
                    decision.decision.value,
                    json.dumps([
                        {"rule_id": m.rule_id, "severity": m.severity.value, "message": m.message}
                        for m in decision.matched_rules
                    ], separators=(",", ":")),
                    json.dumps(intent.as_dict(), sort_keys=True, separators=(",", ":")),
                    signature,
                    time.time(),
                ),
            )
            if commit:
                self._conn.commit()

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

    def record_authorization_artifacts(
        self,
        artifacts: dict,
        *,
        agent_signature: str | None = None,
    ) -> None:
        decision = artifacts["decision_receipt"]
        execution = artifacts.get("execution_authorization")
        decision_payload = decision["payload"]
        authorization_id = (
            execution["payload"]["authorization_id"]
            if execution is not None
            else hashlib.sha256(
                json.dumps(decision, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
        )
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO authorization_artifacts "
                    "(authorization_id, intent_id, agent_id, decision_json, "
                    "execution_authorization_json, agent_signature, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        authorization_id,
                        decision_payload["intent"]["intent_id"],
                        decision_payload["intent"]["agent_id"],
                        json.dumps(decision, sort_keys=True, separators=(",", ":")),
                        json.dumps(execution, sort_keys=True, separators=(",", ":"))
                        if execution is not None else None,
                        agent_signature,
                        time.time(),
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                self._conn.rollback()
                raise ValueError("authorization artifacts already recorded") from exc

    def authorization_by_id(self, authorization_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT decision_json, execution_authorization_json, agent_signature "
                "FROM authorization_artifacts WHERE authorization_id = ?",
                (authorization_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "decision_receipt": json.loads(row[0]),
            "execution_authorization": json.loads(row[1]) if row[1] else None,
            "agent_signature": row[2],
        }

    def audit_by_intent(self, intent_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT intent_id, agent_id, payee, asset, network, amount, decision, "
                "matched_rules_json, intent_json, signature, created_at "
                "FROM audit_log WHERE intent_id = ? ORDER BY created_at DESC LIMIT 1",
                (intent_id,),
            ).fetchone()
        if row is None:
            return None
        columns = [
            "intent_id", "agent_id", "payee", "asset", "network", "amount",
            "decision", "matched_rules_json", "intent_json", "signature", "created_at",
        ]
        item = dict(zip(columns, row))
        item["matched_rules"] = json.loads(item.pop("matched_rules_json"))
        item["intent"] = json.loads(item.pop("intent_json"))
        return item

    def authorization_by_intent(self, intent_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT authorization_id FROM authorization_artifacts WHERE intent_id = ?",
                (intent_id,),
            ).fetchone()
        return self.authorization_by_id(row[0]) if row else None

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


    def register_identity(self, identity) -> None:
        """Persist a new cryptographic agent identity."""
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO identities "
                    "(identity_id, agent_id, identity_json, identity_sha256, status, "
                    "issued_at, expires_at, revoked_at, created_at) "
                    "VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?, NULL, ?)",
                    (
                        identity.key_id,
                        identity.agent_id,
                        json.dumps(identity.__dict__, sort_keys=True, separators=(",", ":")),
                        identity.digest,
                        identity.issued_at,
                        identity.expires_at,
                        time.time(),
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                self._conn.rollback()
                raise ValueError("identity_id already registered") from exc

    def identity(self, identity_id: str):
        from .models import AgentIdentity

        with self._lock:
            row = self._conn.execute(
                "SELECT identity_json FROM identities WHERE identity_id = ?",
                (identity_id,),
            ).fetchone()
        if row is None:
            return None
        return AgentIdentity(**json.loads(row[0]))

    def identity_is_active(self, identity_id: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            row = self._conn.execute(
                "SELECT status, expires_at FROM identities WHERE identity_id = ?",
                (identity_id,),
            ).fetchone()
        return bool(row and row[0] == 'ACTIVE' and (row[1] is None or now < row[1]))

    def revoke_identity(self, identity_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE identities SET status = 'REVOKED', revoked_at = ? "
                "WHERE identity_id = ? AND status = 'ACTIVE'",
                (time.time(), identity_id),
            )
            if cursor.rowcount != 1:
                self._conn.rollback()
                return False
            self._conn.commit()
            return True

    def register_capability(self, capability: Capability) -> None:
        """Persist a new capability and its identity->capability graph edge atomically."""
        with self.transaction():
            try:
                self._conn.execute(
                    "INSERT INTO capabilities "
                    "(capability_id, agent_id, version, capability_json, capability_sha256, "
                    "status, issued_at, expires_at, revoked_at, created_at) "
                    "VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, NULL, ?)",
                    (
                        capability.capability_id,
                        capability.agent_id,
                        capability.version,
                        json.dumps(capability.__dict__, sort_keys=True, separators=(",", ":")),
                        capability.digest,
                        capability.issued_at,
                        capability.expires_at,
                        time.time(),
                    ),
                )
                if capability.identity_id:
                    self._conn.execute(
                        "INSERT INTO authority_edges "
                        "(edge_id, source_type, source_id, relation, target_type, target_id, "
                        "status, created_at, revoked_at) VALUES (?, 'identity', ?, 'HOLDS', 'capability', ?, 'ACTIVE', ?, NULL)",
                        (
                            str(uuid.uuid4()),
                            capability.identity_id,
                            capability.capability_id,
                            time.time(),
                        ),
                    )
            except sqlite3.IntegrityError as exc:
                raise ValueError("capability_id or authority edge already registered") from exc

    def capability(self, capability_id: str) -> Capability | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT capability_json FROM capabilities WHERE capability_id = ?",
                (capability_id,),
            ).fetchone()
        if row is None:
            return None
        data = json.loads(row[0])
        data["allowed_actions"] = tuple(data.get("allowed_actions", ()))
        data["allowed_targets"] = tuple(data.get("allowed_targets", ()))
        data["allowed_resources"] = tuple(data.get("allowed_resources", ()))
        data["allowed_networks"] = tuple(data.get("allowed_networks", ()))
        data["allowed_assets"] = tuple(data.get("allowed_assets", ()))
        data["conditions"] = tuple(data.get("conditions", ()))
        return Capability(**data)

    def capability_status(self, capability_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT status FROM capabilities WHERE capability_id = ?",
                (capability_id,),
            ).fetchone()
        return row[0] if row else None

    def revoke_capability(self, capability_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE capabilities SET status = 'REVOKED', revoked_at = ? "
                "WHERE capability_id = ? AND status = 'ACTIVE'",
                (time.time(), capability_id),
            )
            if cursor.rowcount != 1:
                self._conn.rollback()
                return False
            self._conn.commit()
            return True

    def capability_is_active(self, capability_id: str, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            row = self._conn.execute(
                "SELECT status, expires_at FROM capabilities WHERE capability_id = ?",
                (capability_id,),
            ).fetchone()
        return bool(row and row[0] == 'ACTIVE' and (row[1] is None or now < row[1]))

    def record_authority_edge(self, edge, *, commit: bool = True) -> None:
        """Persist one typed authority-graph edge."""
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO authority_edges "
                    "(edge_id, source_type, source_id, relation, target_type, target_id, "
                    "status, created_at, revoked_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        edge.edge_id,
                        edge.source_type,
                        edge.source_id,
                        edge.relation,
                        edge.target_type,
                        edge.target_id,
                        edge.status,
                        edge.created_at,
                        edge.revoked_at,
                    ),
                )
                if commit:
                    self._conn.commit()
            except sqlite3.IntegrityError as exc:
                if commit:
                    self._conn.rollback()
                raise ValueError("authority edge already exists") from exc

    def authority_edges(
        self,
        *,
        source_type: str | None = None,
        source_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        active_only: bool = True,
    ) -> list[dict]:
        clauses = []
        params: list = []
        for column, value in (
            ("source_type", source_type),
            ("source_id", source_id),
            ("target_type", target_type),
            ("target_id", target_id),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                params.append(value)
        if active_only:
            clauses.append("status = 'ACTIVE'")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self._lock:
            rows = self._conn.execute(
                "SELECT edge_id, source_type, source_id, relation, target_type, "
                "target_id, status, created_at, revoked_at "
                f"FROM authority_edges{where} ORDER BY created_at ASC",
                tuple(params),
            ).fetchall()
        columns = [
            "edge_id", "source_type", "source_id", "relation", "target_type",
            "target_id", "status", "created_at", "revoked_at",
        ]
        return [dict(zip(columns, row)) for row in rows]

    def revoke_authority_edge(self, edge_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE authority_edges SET status = 'REVOKED', revoked_at = ? "
                "WHERE edge_id = ? AND status = 'ACTIVE'",
                (time.time(), edge_id),
            )
            if cursor.rowcount != 1:
                self._conn.rollback()
                return False
            self._conn.commit()
            return True

    def register_delegated_capability(self, capability, parent_capability_id: str) -> str:
        """Atomically register a delegated capability and its graph edge."""
        edge_id = str(uuid.uuid4())
        with self.transaction():
            parent = self._conn.execute(
                "SELECT capability_id, status FROM capabilities WHERE capability_id = ?",
                (parent_capability_id,),
            ).fetchone()
            if parent is None:
                raise LookupError("parent capability not found")
            if parent[1] != "ACTIVE":
                raise PermissionError("parent capability is not active")
            try:
                self._conn.execute(
                    "INSERT INTO capabilities "
                    "(capability_id, agent_id, version, capability_json, capability_sha256, "
                    "status, issued_at, expires_at, revoked_at, created_at) "
                    "VALUES (?, ?, ?, ?, ?, 'ACTIVE', ?, ?, NULL, ?)",
                    (
                        capability.capability_id,
                        capability.agent_id,
                        capability.version,
                        json.dumps(capability.__dict__, sort_keys=True, separators=(",", ":")),
                        capability.digest,
                        capability.issued_at,
                        capability.expires_at,
                        time.time(),
                    ),
                )
                self._conn.execute(
                    "INSERT INTO authority_edges "
                    "(edge_id, source_type, source_id, relation, target_type, target_id, "
                    "status, created_at, revoked_at) VALUES (?, 'capability', ?, 'DELEGATES', 'capability', ?, 'ACTIVE', ?, NULL)",
                    (
                        edge_id,
                        parent_capability_id,
                        capability.capability_id,
                        time.time(),
                    ),
                )
                if capability.identity_id:
                    self._conn.execute(
                        "INSERT INTO authority_edges "
                        "(edge_id, source_type, source_id, relation, target_type, target_id, "
                        "status, created_at, revoked_at) VALUES (?, 'identity', ?, 'HOLDS', 'capability', ?, 'ACTIVE', ?, NULL)",
                        (
                            str(uuid.uuid4()),
                            capability.identity_id,
                            capability.capability_id,
                            time.time(),
                        ),
                    )
            except sqlite3.IntegrityError as exc:
                raise ValueError("capability or authority edge already exists") from exc
        return edge_id

    def record_authority_event(self, event: dict) -> None:
        """Persist one verified authority outcome; duplicate evidence is idempotent."""
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO authority_events "
                    "(event_id, agent_id, capability_id, identity_id, event_type, "
                    "action_type, evidence_ref, metadata_json, occurred_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event["event_id"],
                        event["agent_id"],
                        event["capability_id"],
                        event.get("identity_id"),
                        event["event_type"],
                        event.get("action_type"),
                        event["evidence_ref"],
                        json.dumps(
                            event.get("metadata") or {},
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        event["occurred_at"],
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                self._conn.rollback()
                existing = self._conn.execute(
                    "SELECT 1 FROM authority_events WHERE event_id = ?",
                    (event["event_id"],),
                ).fetchone()
                if existing is None:
                    raise ValueError("authority evidence reference already exists")

    def authority_events(
        self,
        *,
        agent_id: str,
        capability_id: str,
        since: float | None = None,
    ) -> list[dict]:
        clauses = ["agent_id = ?", "capability_id = ?"]
        params: list = [agent_id, capability_id]
        if since is not None:
            clauses.append("occurred_at >= ?")
            params.append(since)
        where = " AND ".join(clauses)
        with self._lock:
            rows = self._conn.execute(
                "SELECT event_id, agent_id, capability_id, identity_id, event_type, "
                "action_type, evidence_ref, metadata_json, occurred_at "
                f"FROM authority_events WHERE {where} ORDER BY occurred_at ASC",
                tuple(params),
            ).fetchall()
        columns = [
            "event_id", "agent_id", "capability_id", "identity_id", "event_type",
            "action_type", "evidence_ref", "metadata_json", "occurred_at",
        ]
        result = []
        for row in rows:
            item = dict(zip(columns, row))
            item["metadata"] = json.loads(item.pop("metadata_json"))
            result.append(item)
        return result

    def set_authority_state(
        self,
        agent_id: str,
        capability_id: str,
        state: str,
        snapshot: dict,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO authority_states "
                "(agent_id, capability_id, state, snapshot_json, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(agent_id, capability_id) DO UPDATE SET "
                "state = excluded.state, snapshot_json = excluded.snapshot_json, "
                "updated_at = excluded.updated_at",
                (
                    agent_id,
                    capability_id,
                    state,
                    json.dumps(snapshot, sort_keys=True, separators=(",", ":")),
                    time.time(),
                ),
            )
            self._conn.commit()

    def latest_authority_state(
        self,
        agent_id: str,
        capability_id: str,
    ) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT state FROM authority_states "
                "WHERE agent_id = ? AND capability_id = ?",
                (agent_id, capability_id),
            ).fetchone()
        return row[0] if row else None

    def register_policy_version(self, signed_policy: dict) -> None:
        """Persist one signed policy version by its exact policy digest."""
        payload = signed_policy["payload"]
        policy_sha256 = payload["policy_sha256"]
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO policy_versions "
                "(policy_sha256, policy_id, version, source_ref, signed_policy_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    policy_sha256,
                    payload["policy_id"],
                    payload["version"],
                    payload["source_ref"],
                    json.dumps(
                        signed_policy,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    time.time(),
                ),
            )
            self._conn.commit()

    def policy_version_by_sha(self, policy_sha256: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT signed_policy_json FROM policy_versions WHERE policy_sha256 = ?",
                (policy_sha256,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def latest_policy_version(self, policy_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT policy_sha256, policy_id, version, source_ref, signed_policy_json "
                "FROM policy_versions WHERE policy_id = ? ORDER BY version DESC LIMIT 1",
                (policy_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "policy_sha256": row[0],
            "policy_id": row[1],
            "version": row[2],
            "source_ref": row[3],
            "signed_policy": json.loads(row[4]),
        }

    def governed_policy_change_by_sha(self, policy_sha256: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT envelope_json FROM governed_policy_changes WHERE policy_sha256 = ?",
                (policy_sha256,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def policy_control(self, policy_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT policy_id, active_policy_sha256, frozen, control_json, updated_at "
                "FROM policy_controls WHERE policy_id = ?",
                (policy_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "policy_id": row[0],
            "active_policy_sha256": row[1],
            "frozen": bool(row[2]),
            "control": json.loads(row[3]),
            "updated_at": row[4],
        }

    def policy_control_action(self, action_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT envelope_json FROM policy_control_actions WHERE action_id = ?",
                (action_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def apply_policy_control(
        self,
        policy_id: str,
        active_policy_sha256: str,
        frozen: bool,
        envelope: dict,
    ) -> None:
        action = envelope["governance_action"]
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO policy_control_actions "
                    "(action_id, action_nonce, policy_id, action, envelope_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        action["action_id"],
                        action["nonce"],
                        policy_id,
                        action["action"],
                        json.dumps(
                            envelope,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        time.time(),
                    ),
                )
                self._conn.execute(
                    "INSERT INTO policy_controls "
                    "(policy_id, active_policy_sha256, frozen, control_json, updated_at) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(policy_id) DO UPDATE SET "
                    "active_policy_sha256 = excluded.active_policy_sha256, "
                    "frozen = excluded.frozen, "
                    "control_json = excluded.control_json, "
                    "updated_at = excluded.updated_at",
                    (
                        policy_id,
                        active_policy_sha256,
                        1 if frozen else 0,
                        json.dumps(
                            envelope,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        time.time(),
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                self._conn.rollback()
                raise ValueError("policy control action already registered") from exc

    def latest_governed_policy_version(self, policy_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT policy_sha256, policy_id, version, parent_sha256, envelope_json "
                "FROM governed_policy_changes WHERE policy_id = ? "
                "ORDER BY version DESC LIMIT 1",
                (policy_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "policy_sha256": row[0],
            "policy_id": row[1],
            "version": row[2],
            "parent_sha256": row[3],
            "envelope": json.loads(row[4]),
        }

    def register_governed_policy_change(
        self,
        signed_policy: dict,
        envelope: dict,
        *,
        governance_approvals: list[dict] | None = None,
    ) -> None:
        payload = signed_policy["payload"]
        action = envelope["governance_action"]
        with self._lock:
            try:
                for approval in governance_approvals or []:
                    approval_payload = approval["payload"]
                    self._conn.execute(
                        "INSERT INTO governance_approvals "
                        "(approval_id, action_digest, governor_id, role, issued_at, "
                        "expires_at, nonce, signed_approval_json, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            approval_payload["approval_id"],
                            approval_payload["action_digest"],
                            approval_payload["governor_id"],
                            approval_payload["role"],
                            approval_payload["issued_at"],
                            approval_payload["expires_at"],
                            approval_payload["nonce"],
                            json.dumps(
                                approval,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            time.time(),
                        ),
                    )
                self._conn.execute(
                    "INSERT INTO policy_versions "
                    "(policy_sha256, policy_id, version, source_ref, signed_policy_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        payload["policy_sha256"],
                        payload["policy_id"],
                        payload["version"],
                        payload["source_ref"],
                        json.dumps(
                            signed_policy,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        time.time(),
                    ),
                )
                self._conn.execute(
                    "INSERT INTO governed_policy_changes "
                    "(policy_sha256, policy_id, version, parent_sha256, action_id, action_nonce, "
                    "governance_policy_sha256, envelope_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        payload["policy_sha256"],
                        payload["policy_id"],
                        payload["version"],
                        payload.get("parent_sha256"),
                        action["action_id"],
                        action["nonce"],
                        envelope["governance_policy_sha256"],
                        json.dumps(
                            envelope,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        time.time(),
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                self._conn.rollback()
                raise ValueError("governed policy version or approval already registered") from exc

    def register_authority_reset(
        self,
        signed_reset: dict,
        *,
        governance_approvals: list[dict] | None = None,
    ) -> None:
        """Persist a signed governance reset and optional quorum approvals atomically."""
        payload = signed_reset["payload"]
        with self._lock:
            try:
                for approval in governance_approvals or []:
                    approval_payload = approval["payload"]
                    self._conn.execute(
                        "INSERT INTO governance_approvals "
                        "(approval_id, action_digest, governor_id, role, issued_at, "
                        "expires_at, nonce, signed_approval_json, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            approval_payload["approval_id"],
                            approval_payload["action_digest"],
                            approval_payload["governor_id"],
                            approval_payload["role"],
                            approval_payload["issued_at"],
                            approval_payload["expires_at"],
                            approval_payload["nonce"],
                            json.dumps(
                                approval,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            time.time(),
                        ),
                    )
                self._conn.execute(
                    "INSERT INTO authority_resets "
                    "(reset_id, agent_id, capability_id, governor_id, epoch, reason, "
                    "issued_at, nonce, signed_reset_json, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        payload.get("reset_id", payload.get("action_id")),
                        payload["agent_id"],
                        payload["capability_id"],
                        payload.get("governor_id", "MULTIPARTY"),
                        payload["epoch"],
                        payload["reason"],
                        payload["issued_at"],
                        payload["nonce"],
                        json.dumps(
                            signed_reset,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        time.time(),
                    ),
                )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                self._conn.rollback()
                if governance_approvals:
                    raise ValueError("governance approval or authority reset already registered") from exc
                raise ValueError("authority reset already registered") from exc

    def latest_authority_reset(
        self,
        agent_id: str,
        capability_id: str,
    ) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT signed_reset_json FROM authority_resets "
                "WHERE agent_id = ? AND capability_id = ? "
                "ORDER BY epoch DESC LIMIT 1",
                (agent_id, capability_id),
            ).fetchone()
        return json.loads(row[0]) if row else None

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
