from __future__ import annotations

from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.storage import Storage
from enforcement.local import ExecutionGate
from enforcement.protocol import ExecutionAdapter


class EVMExecutionAdapter(ExecutionAdapter):
    """Fail-closed EVM bridge.

    Required EVM external-state authorizations must target a deployed
    VerigateAtomicStateGuard envelope. The guard performs the state check and
    target call inside the same EVM transaction; an off-chain preflight alone
    is deliberately insufficient.
    """

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

        result = {"chain_id": chain_id, "to": to, "value_wei": value_wei, "data": data}
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

    @staticmethod
    def _atomic_guard_binding(
        authorization: dict[str, Any], external_state: dict[str, Any]
    ) -> dict[str, Any]:
        binding = external_state.get("atomic_guard")
        if not isinstance(binding, dict):
            raise ValueError("EVM state binding is missing atomic_guard commitment")
        guard = binding.get("address")
        oracle = binding.get("oracle")
        reference = binding.get("reference")
        expected = binding.get("expected")
        data_sha256 = binding.get("data_sha256")
        if not all(isinstance(v, str) and v for v in (guard, oracle, reference, expected, data_sha256)):
            raise ValueError("invalid atomic_guard commitment")
        if not reference.startswith("0x") or len(reference) != 66:
            raise ValueError("invalid atomic_guard reference")
        if not expected.startswith("0x") or len(expected) != 66:
            raise ValueError("invalid atomic_guard expected value")
        if len(data_sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in data_sha256):
            raise ValueError("invalid atomic_guard calldata digest")

        action = authorization["payload"]["action"]
        tx = EVMExecutionAdapter._transaction(action)
        if tx["to"].lower() != guard.lower():
            raise ValueError("EVM transaction does not target the committed atomic guard")
        import hashlib
        actual_data_sha256 = hashlib.sha256(tx["data"].encode("utf-8")).hexdigest()
        if actual_data_sha256 != data_sha256.lower():
            raise ValueError("EVM transaction calldata does not match atomic guard commitment")
        return binding

    def execute_bound(
        self,
        authorization: dict[str, Any],
        external_state: dict[str, Any],
        broadcaster: Callable[[dict[str, Any]], Any],
    ) -> Any:
        """Broadcast only a transaction whose on-chain guard enforces state atomically."""
        if external_state.get("kind") != "evm.state":
            raise ValueError("atomic EVM enforcement requires evm.state")
        self._atomic_guard_binding(authorization, external_state)
        tx = self._transaction(authorization["payload"]["action"])
        ok, reason = self.gate.consume(authorization)
        if not ok:
            raise PermissionError(reason)
        return broadcaster(tx)

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
