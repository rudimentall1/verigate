"""Minimal Solana JSON-RPC client for authorized transaction broadcast."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


class SolanaRpcError(RuntimeError):
    """Raised when a Solana JSON-RPC request fails."""


@dataclass(frozen=True)
class SolanaRpcClient:
    endpoint: str
    timeout_seconds: float = 15.0
    transport: Callable[[str, bytes, dict[str, str], float], bytes] | None = None

    def _request(self, method: str, params: list[Any]) -> Any:
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }, separators=(",", ":")).encode("utf-8")
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
            raise SolanaRpcError(f"Solana RPC request failed: {exc}") from exc

        try:
            body = json.loads(raw)
        except (TypeError, json.JSONDecodeError) as exc:
            raise SolanaRpcError("Solana RPC returned invalid JSON") from exc

        if body.get("error") is not None:
            raise SolanaRpcError(
                f"Solana RPC error: {body['error']}"
            )
        return body.get("result")

    def get_latest_blockhash(self) -> dict[str, Any]:
        result = self._request(
            "getLatestBlockhash",
            [{"commitment": "confirmed"}],
        )
        if not isinstance(result, dict):
            raise SolanaRpcError("getLatestBlockhash returned invalid result")
        value = result.get("value")
        if not isinstance(value, dict) or not value.get("blockhash"):
            raise SolanaRpcError("getLatestBlockhash returned no blockhash")
        return value

    def simulate_transaction(self, serialized_transaction: str) -> dict[str, Any]:
        result = self._request(
            "simulateTransaction",
            [
                serialized_transaction,
                {
                    "encoding": "base64",
                    "sigVerify": True,
                    "replaceRecentBlockhash": False,
                },
            ],
        )
        if not isinstance(result, dict):
            raise SolanaRpcError("simulateTransaction returned invalid result")
        return result

    def send_transaction(self, serialized_transaction: str) -> str:
        result = self._request(
            "sendTransaction",
            [
                serialized_transaction,
                {
                    "encoding": "base64",
                    "skipPreflight": False,
                    "preflightCommitment": "confirmed",
                    "maxRetries": 0,
                },
            ],
        )
        if not isinstance(result, str) or not result:
            raise SolanaRpcError("sendTransaction returned no signature")
        return result
