"""Minimal EVM JSON-RPC client for authorized raw transaction broadcast."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


class EvmRpcError(RuntimeError):
    """Raised when an EVM JSON-RPC request fails."""


@dataclass(frozen=True)
class EvmRpcClient:
    endpoint: str
    timeout_seconds: float = 15.0
    transport: Callable[[str, bytes, dict[str, str], float], bytes] | None = None

    def _request(self, method: str, params: list[Any]) -> Any:
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        try:
            if self.transport is not None:
                raw = self.transport(self.endpoint, payload, headers, self.timeout_seconds)
            else:
                request = urllib.request.Request(
                    self.endpoint,
                    data=payload,
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read()
        except (OSError, urllib.error.URLError) as exc:
            raise EvmRpcError(f"EVM RPC request failed: {exc}") from exc

        try:
            body = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise EvmRpcError("EVM RPC returned invalid JSON") from exc
        if body.get("error") is not None:
            raise EvmRpcError(f"EVM RPC error: {body['error']}")
        return body.get("result")

    def chain_id(self) -> int:
        result = self._request("eth_chainId", [])
        if not isinstance(result, str) or not result.startswith("0x"):
            raise EvmRpcError("eth_chainId returned invalid result")
        try:
            return int(result, 16)
        except ValueError as exc:
            raise EvmRpcError("eth_chainId returned invalid hex") from exc

    def send_raw_transaction(self, signed_raw_transaction: str) -> str:
        if (
            not isinstance(signed_raw_transaction, str)
            or not signed_raw_transaction.startswith("0x")
            or len(signed_raw_transaction) <= 2
            or len(signed_raw_transaction[2:]) % 2
            or any(c not in "0123456789abcdefABCDEF" for c in signed_raw_transaction[2:])
        ):
            raise ValueError("invalid signed EVM transaction encoding")
        result = self._request("eth_sendRawTransaction", [signed_raw_transaction])
        if not isinstance(result, str) or not result.startswith("0x"):
            raise EvmRpcError("eth_sendRawTransaction returned no transaction hash")
        return result
