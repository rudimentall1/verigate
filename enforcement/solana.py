"""Fail-closed Solana execution adapter for bound native SOL transfers."""
from __future__ import annotations

from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.storage import Storage
from enforcement.local import ExecutionGate
from enforcement.protocol import ExecutionAdapter
from enforcement.solana_transaction import parse_authorized_native_transfer


class SolanaExecutionAdapter(ExecutionAdapter):
    def __init__(self, storage: Storage, public_key: Ed25519PublicKey):
        self.gate = ExecutionGate(storage, public_key)

    @staticmethod
    def _transaction(action: dict[str, Any]) -> dict[str, Any]:
        # Parsing is deliberately repeated at the execution boundary. The
        # authorization binds the exact serialized bytes, while this parser
        # independently proves their sender, recipient and amount semantics.
        parse_authorized_native_transfer(action)
        metadata = action["metadata"]
        return {
            "encoding": "base64",
            "serialized_transaction": metadata["solana_transaction"],
        }

    def validate(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        try:
            self._transaction(authorization["payload"]["action"])
        except (KeyError, TypeError, ValueError) as exc:
            return False, str(exc)
        return self.gate.validate(authorization)

    def consume(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        ok, reason = self.validate(authorization)
        if not ok:
            return False, reason
        return self.gate.consume(authorization)

    def execute_after_consume(
        self,
        authorization: dict[str, Any],
        broadcaster: Callable[[dict[str, Any]], Any],
    ) -> Any:
        action = authorization["payload"]["action"]
        tx = self._transaction(action)
        return broadcaster(tx)

    def execute(
        self,
        authorization: dict[str, Any],
        broadcaster: Callable[[dict[str, Any]], Any],
    ) -> Any:
        # Validate transaction semantics before consuming the one-time grant.
        action = authorization["payload"]["action"]
        self._transaction(action)
        ok, reason = self.gate.consume(authorization)
        if not ok:
            raise PermissionError(reason)
        return self.execute_after_consume(authorization, broadcaster)
