"""Dependency-light EVM execution adapter."""
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
        signed_raw_transaction = tx.get("signed_raw_transaction")

        if not isinstance(chain_id, int) or chain_id <= 0:
            raise ValueError("invalid EVM chain_id")
        if not isinstance(to, str) or not to:
            raise ValueError("invalid EVM to address")
        if not isinstance(value_wei, int) or value_wei < 0:
            raise ValueError("invalid EVM value_wei")
        if not isinstance(data, str) or not data.startswith("0x"):
            raise ValueError("invalid EVM calldata")

        result = {
            "chain_id": chain_id,
            "to": to,
            "value_wei": value_wei,
            "data": data,
        }
        if signed_raw_transaction is not None:
            if (
                not isinstance(signed_raw_transaction, str)
                or not signed_raw_transaction.startswith("0x")
                or len(signed_raw_transaction) <= 2
                or len(signed_raw_transaction[2:]) % 2
                or any(c not in "0123456789abcdefABCDEF" for c in signed_raw_transaction[2:])
            ):
                raise ValueError("invalid signed EVM transaction encoding")
            result["signed_raw_transaction"] = signed_raw_transaction
        return result

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
