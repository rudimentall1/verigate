"""Dependency-light EVM execution adapter.

The adapter extracts the exact EVM transaction envelope from the signed
normalized action, validates it, then consumes the one-time capability before
handing the canonical transaction to a broadcaster.
"""
from __future__ import annotations

from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.storage import Storage
from enforcement.local import ExecutionGate
from enforcement.protocol import ExecutionAdapter


class EVMExecutionAdapter(ExecutionAdapter):
    """Fail-closed EVM bridge without taking a web3 dependency."""

    def __init__(self, storage: Storage, public_key: Ed25519PublicKey):
        self.gate = ExecutionGate(storage, public_key)

    @staticmethod
    def _transaction(action: dict[str, Any]) -> dict[str, Any]:
        metadata = action.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("authorized action is missing metadata")
        tx = metadata.get("evm_transaction")
        if not isinstance(tx, dict):
            raise ValueError("authorized action is missing evm_transaction")
        chain_id = tx.get("chain_id")
        to = tx.get("to")
        value_wei = tx.get("value_wei", 0)
        data = tx.get("data", "0x")
        if not isinstance(chain_id, int) or chain_id <= 0:
            raise ValueError("invalid EVM chain_id")
        if not isinstance(to, str) or not to:
            raise ValueError("invalid EVM to address")
        if not isinstance(value_wei, int) or value_wei < 0:
            raise ValueError("invalid EVM value_wei")
        if not isinstance(data, str) or not data.startswith("0x"):
            raise ValueError("invalid EVM calldata")
        return {"chain_id": chain_id, "to": to, "value_wei": value_wei, "data": data}

    def consume(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        action = authorization["payload"]["action"]
        try:
            self._transaction(action)
        except (KeyError, TypeError, ValueError) as exc:
            return False, str(exc)
        return self.gate.consume(authorization)

    def execute(
        self,
        authorization: dict[str, Any],
        broadcaster: Callable[[dict[str, Any]], Any],
    ) -> Any:
        """Consume authorization and broadcast only the signed transaction envelope."""
        action = authorization["payload"]["action"]
        tx = self._transaction(action)
        ok, reason = self.gate.consume(authorization)
        if not ok:
            raise PermissionError(reason)
        return broadcaster(tx)
