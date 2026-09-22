"""Minimal CoinMarketCap RWA API client.

Uses the dedicated RWA v5 endpoints. The transport is injectable so the
adapter is fully testable without network access.
"""
from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import CmcRwaQuote


class CmcApiError(RuntimeError):
    """Raised when CoinMarketCap returns an unusable response."""


Transport = Callable[[str, dict[str, str], float], dict[str, Any]]


def _http_get_json(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class CmcRwaClient:
    """CoinMarketCap RWA API client with stable-id-first lookup helpers."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = "https://pro-api.coinmarketcap.com",
        timeout: float = 10.0,
        transport: Transport | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport or _http_get_json

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        query = urlencode({key: value for key, value in params.items() if value is not None})
        url = f"{self.base_url}{path}?{query}" if query else f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-CMC_PRO_API_KEY"] = self.api_key
        payload = self.transport(url, headers, self.timeout)
        status = payload.get("status") or {}
        if status.get("error_code"):
            raise CmcApiError(
                f"CoinMarketCap error {status.get('error_code')}: "
                f"{status.get('error_message') or 'unknown error'}"
            )
        return payload

    @staticmethod
    def _selector(**selectors: Any) -> dict[str, Any]:
        active = {key: value for key, value in selectors.items() if value is not None}
        if len(active) != 1:
            raise ValueError("provide exactly one of rwa_id, rwa_slug, or symbol")
        return active
    def resolve(self, *, rwa_id: int | None = None, rwa_slug: str | None = None,
                symbol: str | None = None) -> dict[str, Any]:
        params = self._selector(rwa_id=rwa_id, rwa_slug=rwa_slug, symbol=symbol)
        return self._get("/v5/real-world-assets/map", params)

    def quote(self, *, rwa_id: int | None = None, rwa_slug: str | None = None,
              symbol: str | None = None, convert: str = "USD") -> CmcRwaQuote:
        params = self._selector(rwa_id=rwa_id, rwa_slug=rwa_slug, symbol=symbol)
        params["convert"] = convert
        payload = self._get("/v5/real-world-assets/quotes/latest", params)
        return self._parse_quote(payload)

    @staticmethod
    def _parse_quote(payload: dict[str, Any]) -> CmcRwaQuote:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise CmcApiError("CoinMarketCap RWA response has no data object")

        if "rwa_id" in data:
            record = data
        else:
            records = [value for value in data.values() if isinstance(value, dict)]
            if len(records) != 1:
                raise CmcApiError("expected exactly one RWA quote record")
            record = records[0]

        status = payload.get("status") or {}
        return CmcRwaQuote.from_record(
            record,
            source_timestamp=status.get("timestamp"),
        )
