"""Health metrics and alert thresholds for the durable wallet-governance outbox."""
from __future__ import annotations

from typing import Any, Iterable


def build_wallet_governance_outbox_health(
    events: Iterable[dict[str, Any]],
    *,
    now: float | None = None,
    max_pending_age_seconds: float = 300.0,
    max_pending_count: int = 100,
    max_attempts: int = 10,
) -> dict[str, Any]:
    """Build a deterministic health report from Storage outbox event records."""
    import math
    import time

    if now is None:
        now = time.time()
    numeric_thresholds = {
        "now": now,
        "max_pending_age_seconds": max_pending_age_seconds,
    }
    for name, value in numeric_thresholds.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a finite number")
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be a finite non-negative number")
    for name, value in (
        ("max_pending_count", max_pending_count),
        ("max_attempts", max_attempts),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")

    materialized = list(events)
    pending: list[dict[str, Any]] = []
    delivered_count = 0
    last_delivered_at = None
    for event in materialized:
        if not isinstance(event, dict):
            raise ValueError("outbox events must be dictionaries")
        status = event.get("status")
        if status not in {"PENDING", "DELIVERED"}:
            raise ValueError("outbox event has an unknown status")
        attempts = event.get("attempts")
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
            raise ValueError("outbox event attempts must be a non-negative integer")
        if not isinstance(event.get("action_id"), str) or not event["action_id"]:
            raise ValueError("outbox event action_id is required")
        if not isinstance(event.get("installation_principal"), str) or not event["installation_principal"]:
            raise ValueError("outbox event installation_principal is required")
        created_at = event.get("created_at")
        if (
            isinstance(created_at, bool)
            or not isinstance(created_at, (int, float))
            or not math.isfinite(created_at)
            or created_at < 0
        ):
            raise ValueError("outbox event created_at must be a finite non-negative timestamp")
        if status == "PENDING":
            pending.append(event)
        else:
            delivered_count += 1
            delivered_at = event.get("delivered_at")
            if delivered_at is not None:
                if (
                    isinstance(delivered_at, bool)
                    or not isinstance(delivered_at, (int, float))
                    or not math.isfinite(delivered_at)
                    or delivered_at < 0
                ):
                    raise ValueError("outbox delivered_at must be a finite non-negative timestamp")
                last_delivered_at = (
                    delivered_at if last_delivered_at is None
                    else max(last_delivered_at, delivered_at)
                )

    oldest_pending_age = (
        max(0.0, now - min(event["created_at"] for event in pending))
        if pending else None
    )
    max_pending_attempts = max((event["attempts"] for event in pending), default=0)
    pending_principals = {event["installation_principal"] for event in pending}
    alerts: list[str] = []
    if len(pending) > max_pending_count:
        alerts.append("PENDING_QUEUE_TOO_LARGE")
    if oldest_pending_age is not None and oldest_pending_age > max_pending_age_seconds:
        alerts.append("OLDEST_PENDING_EVENT_TOO_OLD")
    if max_pending_attempts > max_attempts:
        alerts.append("PENDING_EVENT_RETRY_LIMIT_EXCEEDED")

    return {
        "status": "UNHEALTHY" if len(alerts) > 1 else "DEGRADED" if alerts else "HEALTHY",
        "alerts": alerts,
        "metrics": {
            "total_count": len(materialized),
            "pending_count": len(pending),
            "delivered_count": delivered_count,
            "oldest_pending_age_seconds": oldest_pending_age,
            "max_pending_attempts": max_pending_attempts,
            "pending_principal_count": len(pending_principals),
            "last_delivered_at": last_delivered_at,
        },
    }
