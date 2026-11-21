"""Separately administered append-only transparency log for wallet governance history.

The log must use its own SQLite file and Ed25519 signing key, administered outside
the Verigate service. The verifier's trust comes from an out-of-band checkpoint
digest plus the independently distributed log public key, not from the package.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


WALLET_GOVERNANCE_LOG_PROTOCOL = "verigate-wallet-governance-log-v1"
_ZERO_HASH = "0" * 64
_PRINCIPAL = re.compile(r"^anna-installation:[0-9a-f]{64}$")


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _decode_b64(value: Any, description: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (TypeError, ValueError):
        raise ValueError(f"{description} is not valid base64") from None


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _history_order(envelopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        envelopes,
        key=lambda item: item["action"]["action_id"],
    )


def _validate_history(
    installation_principal: str,
    envelopes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(installation_principal, str) or not _PRINCIPAL.fullmatch(installation_principal):
        raise ValueError("wallet transparency log installation principal is invalid")
    if not isinstance(envelopes, list) or not envelopes:
        raise ValueError("wallet transparency log history must be a non-empty list")

    by_action: dict[str, dict[str, Any]] = {}
    for envelope in envelopes:
        if not isinstance(envelope, dict):
            raise ValueError("wallet transparency log envelope is malformed")
        action = envelope.get("action")
        if not isinstance(action, dict):
            raise ValueError("wallet transparency log action is malformed")
        action_id = action.get("action_id")
        if (
            not isinstance(action_id, str)
            or not action_id
            or action_id in by_action
            or action.get("action") not in {"WALLET_ENROLL", "WALLET_REVOKE"}
        ):
            raise ValueError("wallet transparency log action identity is invalid or duplicated")
        if (
            action.get("action") == "WALLET_ENROLL"
            and action.get("installation_principal") != installation_principal
        ):
            raise ValueError("wallet transparency log enrollment action has another installation principal")
        by_action[action_id] = envelope
    return _history_order(envelopes), by_action


class WalletGovernanceTransparencyLog:
    """Append governance envelopes and issue signed, hash-chained checkpoints.

    This class is the writer-side component. Deploy it as a separate service with
    a database file and signing key that are not writable by the Verigate process.
    SQLite triggers prevent ordinary UPDATE/DELETE operations; the external
    checkpoint pin detects rollback or replacement of the log database.
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        log_id: str,
        signing_key: Ed25519PrivateKey,
    ):
        if not isinstance(log_id, str) or not log_id.strip():
            raise ValueError("wallet transparency log_id is required")
        if not isinstance(signing_key, Ed25519PrivateKey):
            raise TypeError("wallet transparency signing key must be Ed25519")
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.log_id = log_id
        self.signing_key = signing_key
        public_raw = signing_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        self.public_key_b64 = _b64(public_raw)
        self.signer_key_id = hashlib.sha256(public_raw).hexdigest()
        self._connection = sqlite3.connect(self.db_path, timeout=30)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS wallet_governance_log_entries (
                installation_principal TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                log_id TEXT NOT NULL,
                action_id TEXT NOT NULL,
                entry_sha256 TEXT NOT NULL,
                entry_payload_json TEXT NOT NULL,
                envelope_json TEXT NOT NULL,
                PRIMARY KEY (installation_principal, sequence),
                UNIQUE (installation_principal, action_id),
                UNIQUE (installation_principal, entry_sha256)
            );

            CREATE TABLE IF NOT EXISTS wallet_governance_log_checkpoints (
                installation_principal TEXT NOT NULL,
                checkpoint_sequence INTEGER NOT NULL,
                checkpoint_sha256 TEXT NOT NULL UNIQUE,
                checkpoint_payload_json TEXT NOT NULL,
                signature_b64 TEXT NOT NULL,
                signer_public_key_b64 TEXT NOT NULL,
                PRIMARY KEY (installation_principal, checkpoint_sequence)
            );

            CREATE TRIGGER IF NOT EXISTS wallet_governance_log_entries_no_replace
            BEFORE INSERT ON wallet_governance_log_entries
            WHEN EXISTS (
                SELECT 1 FROM wallet_governance_log_entries
                WHERE installation_principal = NEW.installation_principal
                  AND (
                    sequence = NEW.sequence
                    OR action_id = NEW.action_id
                    OR entry_sha256 = NEW.entry_sha256
                  )
            )
            BEGIN
                SELECT RAISE(ABORT, 'wallet governance log entries cannot be replaced');
            END;

            CREATE TRIGGER IF NOT EXISTS wallet_governance_log_checkpoints_no_replace
            BEFORE INSERT ON wallet_governance_log_checkpoints
            WHEN EXISTS (
                SELECT 1 FROM wallet_governance_log_checkpoints
                WHERE installation_principal = NEW.installation_principal
                  AND (
                    checkpoint_sequence = NEW.checkpoint_sequence
                    OR checkpoint_sha256 = NEW.checkpoint_sha256
                  )
            )
            BEGIN
                SELECT RAISE(ABORT, 'wallet governance log checkpoints cannot be replaced');
            END;

            CREATE TRIGGER IF NOT EXISTS wallet_governance_log_entries_no_update
            BEFORE UPDATE ON wallet_governance_log_entries
            BEGIN
                SELECT RAISE(ABORT, 'wallet governance log entries are append-only');
            END;

            CREATE TRIGGER IF NOT EXISTS wallet_governance_log_entries_no_delete
            BEFORE DELETE ON wallet_governance_log_entries
            BEGIN
                SELECT RAISE(ABORT, 'wallet governance log entries are append-only');
            END;

            CREATE TRIGGER IF NOT EXISTS wallet_governance_log_checkpoints_no_update
            BEFORE UPDATE ON wallet_governance_log_checkpoints
            BEGIN
                SELECT RAISE(ABORT, 'wallet governance log checkpoints are append-only');
            END;

            CREATE TRIGGER IF NOT EXISTS wallet_governance_log_checkpoints_no_delete
            BEFORE DELETE ON wallet_governance_log_checkpoints
            BEGIN
                SELECT RAISE(ABORT, 'wallet governance log checkpoints are append-only');
            END;
            """
        )
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def export_public_key_pem(self, path: str | Path) -> Path:
        """Write the public key in PEM form for out-of-band verifier provisioning."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        public_key_pem = self.signing_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        destination.write_bytes(public_key_pem)
        return destination

    def append_envelope(
        self,
        installation_principal: str,
        envelope: dict[str, Any],
    ) -> dict[str, Any]:
        """Append one newly accepted governance envelope from an external event stream.

        This is the preferred per-action ingestion API for a separately operated
        log service. It reuses the current immutable history and returns a fresh
        signed checkpoint after a new action is committed.
        """
        if not isinstance(envelope, dict) or not isinstance(envelope.get("action"), dict):
            raise ValueError("wallet transparency log envelope is malformed")
        action_id = envelope["action"].get("action_id")
        if not isinstance(action_id, str) or not action_id:
            raise ValueError("wallet transparency log action ID is invalid")
        rows = self._connection.execute(
            "SELECT envelope_json FROM wallet_governance_log_entries "
            "WHERE installation_principal = ? ORDER BY sequence",
            (installation_principal,),
        ).fetchall()
        current_history = [json.loads(row[0]) for row in rows]
        existing = next(
            (
                item for item in current_history
                if item.get("action", {}).get("action_id") == action_id
            ),
            None,
        )
        if existing is not None:
            if canonical(existing) != canonical(envelope):
                raise ValueError(
                    f"wallet transparency log action {action_id} is immutable and cannot be rewritten"
                )
        else:
            current_history.append(envelope)
        return self.checkpoint_history(
            installation_principal,
            current_history,
        )

    def checkpoint_history(
        self,
        installation_principal: str,
        envelopes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Append any new envelopes and return the latest signed checkpoint bundle.

        Existing action IDs are immutable. Supplying a history that omits a
        previously anchored action is rejected rather than silently treating it
        as a complete new log.
        """
        ordered_history, history_by_action = _validate_history(
            installation_principal, envelopes,
        )
        history_sha256 = digest(ordered_history)
        connection = self._connection
        connection.execute("BEGIN IMMEDIATE")
        try:
            stored_rows = connection.execute(
                "SELECT sequence, action_id, entry_sha256, entry_payload_json, envelope_json, log_id "
                "FROM wallet_governance_log_entries "
                "WHERE installation_principal = ? ORDER BY sequence",
                (installation_principal,),
            ).fetchall()
            stored_by_action = {row[1]: row for row in stored_rows}
            if any(row[5] != self.log_id for row in stored_rows):
                raise ValueError("wallet transparency log database is already bound to another log_id")
            omitted = sorted(set(stored_by_action) - set(history_by_action))
            if omitted:
                raise ValueError(
                    "wallet transparency log history omits previously anchored actions: "
                    + ", ".join(omitted)
                )

            for action_id, row in stored_by_action.items():
                expected_json = canonical(history_by_action[action_id]).decode("utf-8")
                if row[4] != expected_json:
                    raise ValueError(
                        f"wallet transparency log action {action_id} is immutable and cannot be rewritten"
                    )

            sequence = len(stored_rows)
            previous_entry_sha256 = stored_rows[-1][2] if stored_rows else _ZERO_HASH
            for envelope in envelopes:
                action_id = envelope["action"]["action_id"]
                if action_id in stored_by_action:
                    continue
                sequence += 1
                entry_payload = {
                    "protocol": WALLET_GOVERNANCE_LOG_PROTOCOL,
                    "log_id": self.log_id,
                    "installation_principal": installation_principal,
                    "sequence": sequence,
                    "previous_entry_sha256": previous_entry_sha256,
                    "action_id": action_id,
                    "envelope_sha256": digest(envelope),
                    "envelope": envelope,
                }
                entry_sha256 = digest(entry_payload)
                connection.execute(
                    "INSERT INTO wallet_governance_log_entries "
                    "(installation_principal, sequence, log_id, action_id, entry_sha256, "
                    "entry_payload_json, envelope_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        installation_principal,
                        sequence,
                        self.log_id,
                        action_id,
                        entry_sha256,
                        canonical(entry_payload).decode("utf-8"),
                        canonical(envelope).decode("utf-8"),
                    ),
                )
                previous_entry_sha256 = entry_sha256
                stored_by_action[action_id] = (
                    sequence, action_id, entry_sha256,
                    canonical(entry_payload).decode("utf-8"),
                    canonical(envelope).decode("utf-8"),
                )

            entry_rows = connection.execute(
                "SELECT entry_payload_json, entry_sha256 "
                "FROM wallet_governance_log_entries "
                "WHERE installation_principal = ? ORDER BY sequence",
                (installation_principal,),
            ).fetchall()
            entries = [
                {
                    "payload": json.loads(payload_json),
                    "entry_sha256": entry_sha256,
                }
                for payload_json, entry_sha256 in entry_rows
            ]
            head_entry_sha256 = entries[-1]["entry_sha256"]

            previous_checkpoint = connection.execute(
                "SELECT checkpoint_sequence, checkpoint_sha256, checkpoint_payload_json, "
                "signature_b64, signer_public_key_b64 "
                "FROM wallet_governance_log_checkpoints "
                "WHERE installation_principal = ? ORDER BY checkpoint_sequence DESC LIMIT 1",
                (installation_principal,),
            ).fetchone()
            if previous_checkpoint is not None:
                previous_sequence, previous_checkpoint_sha256 = previous_checkpoint[:2]
                previous_payload = json.loads(previous_checkpoint[2])
                if (
                    previous_payload.get("entry_count") == len(entries)
                    and previous_payload.get("head_entry_sha256") == head_entry_sha256
                    and previous_payload.get("history_sha256") == history_sha256
                    and previous_payload.get("log_id") == self.log_id
                ):
                    connection.commit()
                    return self._bundle_from_rows(
                        installation_principal, entries, previous_checkpoint,
                    )
                checkpoint_sequence = previous_sequence + 1
            else:
                previous_checkpoint_sha256 = _ZERO_HASH
                checkpoint_sequence = 1

            checkpoint_payload = {
                "protocol": WALLET_GOVERNANCE_LOG_PROTOCOL,
                "log_id": self.log_id,
                "installation_principal": installation_principal,
                "checkpoint_sequence": checkpoint_sequence,
                "entry_count": len(entries),
                "head_entry_sha256": head_entry_sha256,
                "history_sha256": history_sha256,
                "previous_checkpoint_sha256": previous_checkpoint_sha256,
                "issued_at": time.time(),
                "signer_key_id": self.signer_key_id,
            }
            checkpoint_sha256 = digest(checkpoint_payload)
            signature = _b64(self.signing_key.sign(canonical(checkpoint_payload)))
            connection.execute(
                "INSERT INTO wallet_governance_log_checkpoints "
                "(installation_principal, checkpoint_sequence, checkpoint_sha256, "
                "checkpoint_payload_json, signature_b64, signer_public_key_b64) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    installation_principal,
                    checkpoint_sequence,
                    checkpoint_sha256,
                    canonical(checkpoint_payload).decode("utf-8"),
                    signature,
                    self.public_key_b64,
                ),
            )
            checkpoint_row = (
                checkpoint_sequence,
                checkpoint_sha256,
                canonical(checkpoint_payload).decode("utf-8"),
                signature,
                self.public_key_b64,
            )
            connection.commit()
            return self._bundle_from_rows(
                installation_principal, entries, checkpoint_row,
            )
        except Exception:
            connection.rollback()
            raise

    def export_bundle(self, installation_principal: str) -> dict[str, Any]:
        """Export the full entry chain and latest signed checkpoint."""
        connection = self._connection
        entry_rows = connection.execute(
            "SELECT entry_payload_json, entry_sha256 "
            "FROM wallet_governance_log_entries "
            "WHERE installation_principal = ? ORDER BY sequence",
            (installation_principal,),
        ).fetchall()
        checkpoint_row = connection.execute(
            "SELECT checkpoint_sequence, checkpoint_sha256, checkpoint_payload_json, "
            "signature_b64, signer_public_key_b64 "
            "FROM wallet_governance_log_checkpoints "
            "WHERE installation_principal = ? ORDER BY checkpoint_sequence DESC LIMIT 1",
            (installation_principal,),
        ).fetchone()
        if not entry_rows or checkpoint_row is None:
            raise LookupError("wallet governance transparency checkpoint not found")
        entries = [
            {"payload": json.loads(payload_json), "entry_sha256": entry_sha256}
            for payload_json, entry_sha256 in entry_rows
        ]
        return self._bundle_from_rows(installation_principal, entries, checkpoint_row)

    def _bundle_from_rows(
        self,
        installation_principal: str,
        entries: list[dict[str, Any]],
        checkpoint_row: tuple[Any, ...],
    ) -> dict[str, Any]:
        checkpoint = {
            "payload": json.loads(checkpoint_row[2]),
            "signature": checkpoint_row[3],
            "algorithm": "Ed25519",
            "signer_public_key_b64": checkpoint_row[4],
            "checkpoint_sha256": checkpoint_row[1],
        }
        return {
            "protocol": WALLET_GOVERNANCE_LOG_PROTOCOL,
            "log_id": self.log_id,
            "installation_principal": installation_principal,
            "entries": entries,
            "checkpoint": checkpoint,
        }


def verify_wallet_governance_transparency_bundle(
    bundle: dict[str, Any],
    *,
    history_envelopes: list[dict[str, Any]],
    installation_principal: str,
    trusted_log_public_key_b64: str | None = None,
    trusted_checkpoint_sha256: str | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Verify a complete log chain and optionally pin its signer and latest head."""
    checks: dict[str, Any] = {}

    def failure(reason: str) -> tuple[bool, str, dict[str, Any]]:
        return False, reason, checks

    if (trusted_log_public_key_b64 is None) != (trusted_checkpoint_sha256 is None):
        return failure(
            "trusted wallet governance log public key and checkpoint digest must be supplied together"
        )
    try:
        ordered_history, history_by_action = _validate_history(
            installation_principal, history_envelopes,
        )
    except ValueError as exc:
        return failure(str(exc))

    if (
        not isinstance(bundle, dict)
        or bundle.get("protocol") != WALLET_GOVERNANCE_LOG_PROTOCOL
        or bundle.get("installation_principal") != installation_principal
        or not isinstance(bundle.get("log_id"), str)
        or not bundle["log_id"]
        or not isinstance(bundle.get("entries"), list)
    ):
        return failure("wallet governance transparency bundle is malformed or scoped to another principal")

    entries = bundle["entries"]
    if not entries:
        return failure("wallet governance transparency entry chain is empty")
    previous_entry_sha256 = _ZERO_HASH
    logged_actions: dict[str, str] = {}
    for expected_sequence, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or not isinstance(entry.get("payload"), dict):
            return failure("wallet governance transparency entry is malformed")
        payload = entry["payload"]
        envelope = payload.get("envelope")
        action_id = payload.get("action_id")
        if (
            payload.get("protocol") != WALLET_GOVERNANCE_LOG_PROTOCOL
            or payload.get("log_id") != bundle["log_id"]
            or payload.get("installation_principal") != installation_principal
            or isinstance(payload.get("sequence"), bool)
            or not isinstance(payload.get("sequence"), int)
            or payload.get("sequence") != expected_sequence
            or payload.get("previous_entry_sha256") != previous_entry_sha256
        ):
            return failure("wallet governance transparency entry sequence or hash chain mismatch")
        if not isinstance(envelope, dict) or not isinstance(action_id, str) or not action_id:
            return failure("wallet governance transparency entry action is malformed")
        if envelope.get("action", {}).get("action_id") != action_id:
            return failure("wallet governance transparency entry action identity mismatch")
        if action_id in logged_actions:
            return failure("wallet governance transparency log contains a duplicate action")
        envelope_sha256 = digest(envelope)
        if payload.get("envelope_sha256") != envelope_sha256:
            return failure("wallet governance transparency envelope digest mismatch")
        entry_sha256 = digest(payload)
        if entry.get("entry_sha256") != entry_sha256:
            return failure("wallet governance transparency entry digest mismatch")
        logged_actions[action_id] = envelope_sha256
        previous_entry_sha256 = entry_sha256

    expected_actions = {
        action_id: digest(envelope)
        for action_id, envelope in history_by_action.items()
    }
    if logged_actions != expected_actions:
        return failure(
            "wallet governance transparency entry chain does not contain the complete exact history"
        )

    checkpoint = bundle.get("checkpoint")
    if not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("payload"), dict):
        return failure("wallet governance transparency checkpoint is missing")
    checkpoint_payload = checkpoint["payload"]
    checkpoint_sha256 = digest(checkpoint_payload)
    if (
        checkpoint.get("algorithm") != "Ed25519"
        or checkpoint.get("checkpoint_sha256") != checkpoint_sha256
        or checkpoint_payload.get("protocol") != WALLET_GOVERNANCE_LOG_PROTOCOL
        or checkpoint_payload.get("log_id") != bundle["log_id"]
        or checkpoint_payload.get("installation_principal") != installation_principal
        or isinstance(checkpoint_payload.get("entry_count"), bool)
        or not isinstance(checkpoint_payload.get("entry_count"), int)
        or checkpoint_payload.get("entry_count") != len(entries)
        or checkpoint_payload.get("head_entry_sha256") != previous_entry_sha256
        or checkpoint_payload.get("history_sha256") != digest(ordered_history)
        or isinstance(checkpoint_payload.get("checkpoint_sequence"), bool)
        or not isinstance(checkpoint_payload.get("checkpoint_sequence"), int)
        or checkpoint_payload["checkpoint_sequence"] < 1
        or not isinstance(checkpoint_payload.get("previous_checkpoint_sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", checkpoint_payload["previous_checkpoint_sha256"])
        or (
            checkpoint_payload.get("checkpoint_sequence") == 1
            and checkpoint_payload["previous_checkpoint_sha256"] != _ZERO_HASH
        )
        or (
            checkpoint_payload.get("checkpoint_sequence") > 1
            and checkpoint_payload["previous_checkpoint_sha256"] == _ZERO_HASH
        )
        or not _finite_number(checkpoint_payload.get("issued_at"))
        or not isinstance(checkpoint_payload.get("signer_key_id"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", checkpoint_payload["signer_key_id"])
    ):
        return failure("wallet governance transparency checkpoint does not bind the complete log head")

    try:
        embedded_public_key = _decode_b64(
            checkpoint.get("signer_public_key_b64"),
            "wallet transparency checkpoint signer public key",
        )
    except ValueError as exc:
        return failure(str(exc))
    if len(embedded_public_key) != 32:
        return failure("wallet transparency checkpoint signer key must be Ed25519")
    embedded_key_id = hashlib.sha256(embedded_public_key).hexdigest()
    if checkpoint_payload.get("signer_key_id") != embedded_key_id:
        return failure("wallet governance transparency checkpoint signer key fingerprint mismatch")

    if trusted_log_public_key_b64 is not None:
        try:
            trusted_public_key = _decode_b64(
                trusted_log_public_key_b64,
                "trusted wallet transparency log public key",
            )
        except ValueError as exc:
            return failure(str(exc))
        if len(trusted_public_key) != 32 or trusted_public_key != embedded_public_key:
            return failure("wallet governance transparency log public key does not match the trusted key")
        if (
            not isinstance(trusted_checkpoint_sha256, str)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", trusted_checkpoint_sha256)
            or checkpoint_sha256 != trusted_checkpoint_sha256.lower()
        ):
            checks["wallet_governance_transparency_anchor"] = {
                "valid": False,
                "pinned": True,
                "checkpoint_sha256": checkpoint_sha256,
                "trusted_checkpoint_sha256": trusted_checkpoint_sha256,
                "reason": "wallet governance transparency checkpoint does not match the trusted latest checkpoint",
            }
            return failure("wallet governance transparency checkpoint digest mismatch")
        public_key_bytes = trusted_public_key
    else:
        public_key_bytes = embedded_public_key

    try:
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            _decode_b64(checkpoint.get("signature"), "wallet transparency checkpoint signature"),
            canonical(checkpoint_payload),
        )
    except (InvalidSignature, TypeError, ValueError):
        return failure("wallet governance transparency checkpoint signature verification failed")

    pinned = trusted_log_public_key_b64 is not None
    checks["wallet_governance_transparency_log_integrity"] = {
        "valid": True,
        "entry_count": len(entries),
        "head_entry_sha256": previous_entry_sha256,
        "history_sha256": digest(ordered_history),
    }
    checks["wallet_governance_transparency_signature"] = {
        "valid": True,
        "log_id": bundle["log_id"],
        "signer_key_id": embedded_key_id,
    }
    checks["wallet_governance_transparency_anchor"] = {
        "valid": True,
        "pinned": pinned,
        "checkpoint_sequence": checkpoint_payload["checkpoint_sequence"],
        "checkpoint_sha256": checkpoint_sha256,
        "trusted_checkpoint_sha256": trusted_checkpoint_sha256,
        "reason": (
            "latest wallet governance checkpoint is independently pinned"
            if pinned
            else "checkpoint signature is valid but no independent log key/checkpoint pin was supplied"
        ),
    }
    return True, "wallet governance transparency log verified", checks
