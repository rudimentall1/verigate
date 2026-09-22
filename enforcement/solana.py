"""Dependency-light Solana execution adapter.

The adapter gates an exact base64-encoded Solana transaction. It does not
need a Solana SDK because the signed transaction is treated as an opaque
wire artifact and is handed unchanged to the broadcaster after authorization.
"""
from __future__ import annotations

import base64
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.storage import Storage
from enforcement.local import ExecutionGate
from enforcement.protocol import ExecutionAdapter


class SolanaExecutionAdapter(ExecutionAdapter):
    def __init__(self, storage: Storage, public_key: Ed25519PublicKey):
        self.gate = ExecutionGate(storage, public_key)

    @staticmethod
    def _transaction(action: dict[str, Any]) -> dict[str, Any]:
        metadata = action.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("authorized action is missing metadata")
        raw = metadata.get("solana_transaction")
        if not isinstance(raw, str) or not raw:
            raise ValueError("authorized action is missing solana_transaction")
        try:
            base64.b64decode(raw, validate=True)
        except (ValueError, TypeError):
            raise ValueError("invalid Solana transaction encoding")
        return {"encoding": "base64", "serialized_transaction": raw}

    def consume(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        try:
            self._transaction(authorization["payload"]["action"])
        except (KeyError, TypeError, ValueError) as exc:
            return False, str(exc)
        return self.gate.consume(authorization)

    def execute(
        self,
        authorization: dict[str, Any],
        broadcaster: Callable[[dict[str, Any]], Any],
    ) -> Any:
        action = authorization["payload"]["action"]
        tx = self._transaction(action)
        ok, reason = self.gate.consume(authorization)
        if not ok:
            raise PermissionError(reason)
        return broadcaster(tx)
