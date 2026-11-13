"""Fail-closed Solana execution adapter for bound native SOL transfers."""
from __future__ import annotations

from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.storage import Storage
from enforcement.local import ExecutionGate
from enforcement.protocol import ExecutionAdapter
from enforcement.solana_transaction import parse_authorized_native_transfer
from enforcement.protocol import ExecutionPermit, _issue_execution_permit


class SolanaExecutionAdapter(ExecutionAdapter):
    def __init__(
        self,
        storage: Storage,
        public_key: Ed25519PublicKey,
        genesis_hash_provider: Callable[[], str] | None = None,
    ):
        self.gate = ExecutionGate(storage, public_key)
        self.genesis_hash_provider = genesis_hash_provider

    def _validate_cluster(self, action: dict[str, Any]) -> None:
        metadata = action.get("metadata")
        expected = metadata.get("solana_genesis_hash") if isinstance(metadata, dict) else None
        if not isinstance(expected, str) or not expected:
            raise ValueError("signed Solana genesis hash is required")
        if self.genesis_hash_provider is None:
            raise ValueError("live Solana genesis hash provider is required")
        actual = self.genesis_hash_provider()
        if not isinstance(actual, str) or not actual:
            raise ValueError("Solana RPC returned an invalid genesis hash")
        if actual != expected:
            raise ValueError(
                f"Solana genesis hash mismatch: authorized={expected} actual={actual}"
            )

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
            action = authorization["payload"]["action"]
            self._validate_cluster(action)
            self._transaction(action)
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            return False, str(exc)
        return self.gate.validate(authorization)

    def consume(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        ok, reason = self.validate(authorization)
        if not ok:
            return False, reason
        return self.gate.consume(authorization)

    def _execute_after_consume(
        self,
        authorization: dict[str, Any],
        broadcaster: Callable[[dict[str, Any]], Any],
    ) -> Any:
        action = authorization["payload"]["action"]
        self._validate_cluster(action)
        tx = self._transaction(action)
        return broadcaster(tx)

    def execute_after_consume(
        self,
        authorization: dict[str, Any],
        broadcaster: Callable[[dict[str, Any]], Any],
        *,
        permit: ExecutionPermit,
    ) -> Any:
        permit.claim(authorization)
        return self._execute_after_consume(authorization, broadcaster)

    def execute(
        self,
        authorization: dict[str, Any],
        broadcaster: Callable[[dict[str, Any]], Any],
    ) -> Any:
        # Validate cluster and transaction semantics before consuming the
        # one-time grant. Recheck the cluster immediately before broadcasting.
        action = authorization["payload"]["action"]
        self._validate_cluster(action)
        self._transaction(action)
        ok, reason = self.gate.consume(authorization)
        if not ok:
            raise PermissionError(reason)
        return self.execute_after_consume(
            authorization, broadcaster, permit=_issue_execution_permit(authorization)
        )
