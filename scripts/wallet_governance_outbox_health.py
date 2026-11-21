#!/usr/bin/env python3
"""Emit machine-readable health metrics for Verigate's wallet-governance outbox."""
from __future__ import annotations

import argparse
import json
import sys

from core.storage import Storage
from core.wallet_governance_monitoring import build_wallet_governance_outbox_health


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, help="Verigate SQLite database containing the durable outbox")
    parser.add_argument("--max-pending-age-seconds", type=float, default=300.0)
    parser.add_argument("--max-pending-count", type=int, default=100)
    parser.add_argument("--max-attempts", type=int, default=10)
    args = parser.parse_args()

    try:
        storage = Storage(args.database)
        try:
            report = build_wallet_governance_outbox_health(
                storage.wallet_governance_outbox_events(),
                max_pending_age_seconds=args.max_pending_age_seconds,
                max_pending_count=args.max_pending_count,
                max_attempts=args.max_attempts,
            )
        finally:
            storage.close()
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            "status": "UNHEALTHY",
            "alerts": ["MONITORING_CHECK_FAILED"],
            "error": str(exc),
        }, sort_keys=True))
        return 2

    print(json.dumps(report, sort_keys=True))
    if report["status"] == "UNHEALTHY":
        return 2
    if report["status"] == "DEGRADED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
