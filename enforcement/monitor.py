"""Network-aware execution confirmation monitor."""
from __future__ import annotations

from typing import Any, Protocol

from enforcement.networks import UnsupportedNetworkError


class ConfirmationProvider(Protocol):
    def confirm_transaction(self, transaction_ref: str) -> dict[str, Any]:
        ...


class ExecutionMonitor:
    """Ask a trusted network RPC provider for the current execution state."""

    def __init__(self, providers: dict[str, ConfirmationProvider]):
        self.providers = {
            name.strip().lower(): provider
            for name, provider in providers.items()
        }

    def check(self, receipt: dict[str, Any]) -> dict[str, Any]:
        payload = receipt["payload"]
        if payload.get("status") != "SUBMITTED":
            return {
                "state": payload.get("status"),
                "transaction_ref": payload.get("transaction_ref"),
            }

        network = payload.get("network")
        transaction_ref = payload.get("transaction_ref")
        if not isinstance(network, str) or not network:
            raise ValueError("execution receipt has no network")
        if not isinstance(transaction_ref, str) or not transaction_ref:
            raise ValueError("execution receipt has no transaction reference")

        provider = self.providers.get(network.lower())
        if provider is None:
            raise UnsupportedNetworkError(
                f"no confirmation provider configured for network: {network}"
            )
        return provider.confirm_transaction(transaction_ref)
