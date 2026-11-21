#!/usr/bin/env python3
"""Reconcile local accepted wallet-governance actions with the independent log."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

from core.wallet_governance_transparency import verify_wallet_governance_transparency_bundle
from core.wallet_governance_transparency_http import WalletGovernanceTransparencyHTTPTransport


TOKEN_ENV = "VERIGATE_WALLET_GOVERNANCE_LOG_BEARER_TOKEN"


def load_local_history_read_only(
    database_path: str | Path,
    installation_principal: str,
) -> list[dict]:
    """Read accepted governance envelopes without creating or migrating the DB."""
    database_uri = Path(database_path).resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)
    try:
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute(
            "SELECT envelope_json FROM wallet_enrollment_governance_actions "
            "WHERE installation_principal = ? ORDER BY created_at",
            (installation_principal,),
        ).fetchall()
        return [json.loads(row[0]) for row in rows]
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--service-url", required=True)
    parser.add_argument("--installation-principal", required=True)
    parser.add_argument("--trusted-log-public-key-b64", required=True)
    parser.add_argument("--trusted-checkpoint-sha256", required=True)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    token = os.environ.get(TOKEN_ENV)
    if not token:
        parser.error(f"{TOKEN_ENV} must be set in the environment")

    try:
        local_history = load_local_history_read_only(
            args.database,
            args.installation_principal,
        )
        if not local_history:
            raise ValueError("local wallet-governance history is empty")
        transport = WalletGovernanceTransparencyHTTPTransport(
            args.service_url,
            bearer_token=token,
            timeout=args.timeout,
        )
        remote_bundle = transport.fetch_bundle(args.installation_principal)
        valid, reason, checks = verify_wallet_governance_transparency_bundle(
            remote_bundle,
            history_envelopes=local_history,
            installation_principal=args.installation_principal,
            trusted_log_public_key_b64=args.trusted_log_public_key_b64,
            trusted_checkpoint_sha256=args.trusted_checkpoint_sha256,
        )
        checkpoint = remote_bundle.get("checkpoint", {})
        checkpoint_sha256 = (
            checkpoint.get("checkpoint_sha256")
            if isinstance(checkpoint, dict) else None
        )
        report = {
            "status": "VERIFIED" if valid else "UNHEALTHY",
            "reason": reason,
            "local_action_count": len(local_history),
            "remote_entry_count": len(remote_bundle.get("entries", []))
            if isinstance(remote_bundle, dict) and isinstance(remote_bundle.get("entries"), list)
            else None,
            "checkpoint_sha256": checkpoint_sha256,
            "checks": checks,
        }
        print(json.dumps(report, sort_keys=True))
        return 0 if valid else 2
    except (
        OSError,
        sqlite3.Error,
        ValueError,
        TypeError,
        LookupError,
        ConnectionError,
        TimeoutError,
        PermissionError,
    ) as exc:
        print(json.dumps({
            "status": "UNHEALTHY",
            "reason": str(exc),
            "alerts": ["WALLET_GOVERNANCE_LOG_RECONCILIATION_FAILED"],
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
