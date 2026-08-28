"""Policy loading. This is the one module in `core/` allowed to import
PyYAML — everything downstream works with plain dicts/dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Policy:
    blocked_payees: list[str] = field(default_factory=list)
    allowed_payees: list[str] | None = None  # None = no allowlist restriction
    allowed_networks: list[str] | None = None
    allowed_assets: list[str] | None = None
    per_tx_cap: dict[str, float] = field(default_factory=dict)  # asset -> max amount
    daily_cap: dict[str, float] = field(default_factory=dict)  # asset -> max amount / 24h
    new_payee_cap: dict[str, float] = field(default_factory=dict)  # tighter cap, first-seen payee
    rate_limit_per_minute: int = 0  # 0 = disabled
    confirmation_required_over: dict[str, float] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def load(path: str | Path) -> "Policy":
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        return Policy(
            blocked_payees=raw.get("blocked_payees", []) or [],
            allowed_payees=raw.get("allowed_payees"),
            allowed_networks=raw.get("allowed_networks"),
            allowed_assets=raw.get("allowed_assets"),
            per_tx_cap=raw.get("per_tx_cap", {}) or {},
            daily_cap=raw.get("daily_cap", {}) or {},
            new_payee_cap=raw.get("new_payee_cap", {}) or {},
            rate_limit_per_minute=int(raw.get("rate_limit_per_minute", 0) or 0),
            confirmation_required_over=raw.get("confirmation_required_over", {}) or {},
            raw=raw,
        )
