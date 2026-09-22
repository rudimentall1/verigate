"""Normalized CoinMarketCap RWA market evidence."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


@dataclass(frozen=True)
class CmcRwaQuote:
    rwa_id: int
    name: str
    symbol: str
    slug: str
    asset_type: str
    rwa_rank: int | None
    has_tokens: bool
    average_tokenized_price: float | None
    tokenized_market_cap: float | None
    tokenized_volume_24h: float | None
    tokens: tuple[dict[str, Any], ...] = ()
    tradfi_markets: tuple[dict[str, Any], ...] = ()
    source_timestamp: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: dict[str, Any], source_timestamp: str | None = None) -> "CmcRwaQuote":
        return cls(
            rwa_id=int(record["rwa_id"]),
            name=str(record["name"]),
            symbol=str(record["symbol"]),
            slug=str(record.get("slug", "")),
            asset_type=str(record["asset_type"]),
            rwa_rank=int(record["rwa_rank"]) if record.get("rwa_rank") is not None else None,
            has_tokens=bool(record.get("has_tokens")),
            average_tokenized_price=_float(record.get("average_tokenized_price")),
            tokenized_market_cap=_float(record.get("tokenized_market_cap")),
            tokenized_volume_24h=_float(record.get("tokenized_volume_24h")),
            tokens=tuple(record.get("tokens") or ()),
            tradfi_markets=tuple(record.get("tradfi_markets") or ()),
            source_timestamp=source_timestamp,
            raw=record,
        )

    def as_evidence(self) -> dict[str, Any]:
        return {
            "provider": "coinmarketcap",
            "rwa_id": self.rwa_id,
            "name": self.name,
            "symbol": self.symbol,
            "slug": self.slug,
            "asset_type": self.asset_type,
            "rwa_rank": self.rwa_rank,
            "has_tokens": self.has_tokens,
            "average_tokenized_price": self.average_tokenized_price,
            "tokenized_market_cap": self.tokenized_market_cap,
            "tokenized_volume_24h": self.tokenized_volume_24h,
            "tokens": list(self.tokens),
            "tradfi_markets": list(self.tradfi_markets),
            "source_timestamp": self.source_timestamp,
        }
