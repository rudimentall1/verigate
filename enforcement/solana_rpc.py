"""Minimal Solana JSON-RPC client for execution and confirmation."""
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
        headers = {"Content-Type": "application/json", "User-Agent": "Verigate/0.1"}
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
            raise SolanaRpcError(f"Solana RPC error: {body['error']}")
        return body.get("result")

    def request_airdrop(self, public_key: str, lamports: int) -> str:
        if not isinstance(public_key, str) or not public_key:
            raise ValueError("invalid Solana public key")
        if not isinstance(lamports, int) or lamports <= 0:
            raise ValueError("invalid Solana airdrop amount")
        result = self._request(
            "requestAirdrop",
            [public_key, lamports, {"commitment": "confirmed"}],
        )
        if not isinstance(result, str) or not result:
            raise SolanaRpcError("requestAirdrop returned no signature")
        return result

    def get_latest_blockhash(self) -> dict[str, Any]:
        result = self._request("getLatestBlockhash", [{"commitment": "confirmed"}])
        if not isinstance(result, dict):
            raise SolanaRpcError("getLatestBlockhash returned invalid result")
        value = result.get("value")
        if not isinstance(value, dict) or not value.get("blockhash"):
            raise SolanaRpcError("getLatestBlockhash returned no blockhash")
        return value

    def simulate_transaction(self, serialized_transaction: str) -> dict[str, Any]:
        result = self._request(
            "simulateTransaction",
            [serialized_transaction, {
                "encoding": "base64",
                "sigVerify": True,
                "replaceRecentBlockhash": False,
            }],
        )
        if not isinstance(result, dict):
            raise SolanaRpcError("simulateTransaction returned invalid result")
        return result

    def send_transaction(self, serialized_transaction: str) -> str:
        result = self._request(
            "sendTransaction",
            [serialized_transaction, {
                "encoding": "base64",
                "skipPreflight": False,
                "preflightCommitment": "confirmed",
                "maxRetries": 0,
            }],
        )
        if not isinstance(result, str) or not result:
            raise SolanaRpcError("sendTransaction returned no signature")
        return result

    def get_signature_status(self, signature: str) -> dict[str, Any] | None:
        if not isinstance(signature, str) or not signature:
            raise ValueError("invalid Solana signature")
        result = self._request(
            "getSignatureStatuses",
            [[signature], {"searchTransactionHistory": True}],
        )
        if not isinstance(result, dict):
            raise SolanaRpcError("getSignatureStatuses returned invalid result")
        values = result.get("value")
        if not isinstance(values, list):
            raise SolanaRpcError("getSignatureStatuses returned invalid values")
        status = values[0] if values else None
        return status if isinstance(status, dict) else None

    def confirm_transaction(self, signature: str) -> dict[str, Any]:
        status = self.get_signature_status(signature)
        if status is None:
            return {"state": "PENDING", "transaction_ref": signature}
        if status.get("err") is not None:
            return {
                "state": "FAILED",
                "transaction_ref": signature,
                "slot": status.get("slot"),
                "confirmations": status.get("confirmations"),
                "error": f"Solana transaction failed: {status['err']}",
                "status": status,
            }
        confirmation_status = status.get("confirmationStatus")
        if confirmation_status in {"confirmed", "finalized"}:
            return {
                "state": "CONFIRMED",
                "transaction_ref": signature,
                "slot": status.get("slot"),
                "confirmations": status.get("confirmations"),
                "confirmation_status": confirmation_status,
                "status": status,
            }
        return {
            "state": "PENDING",
            "transaction_ref": signature,
            "slot": status.get("slot"),
            "confirmations": status.get("confirmations"),
            "confirmation_status": confirmation_status,
            "status": status,
        }
