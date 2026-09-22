"""Universal execution router for Verigate."""
from __future__ import annotations

from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.storage import Storage
from enforcement.evm import EVMExecutionAdapter
from enforcement.local import ExecutionGate
from enforcement.networks import NetworkRegistry, UnsupportedNetworkError
from enforcement.protocol import ExecutionAdapter


class ExecutionRouter:
    """Resolve the safest execution boundary from an authorized action.

    Concrete chain envelopes are routed to their family adapter. Legacy or
    abstract payment capabilities without a wire transaction fall back to the
    local one-time execution gate, preserving backwards compatibility without
    bypassing signature, expiry, or replay checks.
    """

    def __init__(self, registry: NetworkRegistry, storage: Storage, public_key: Ed25519PublicKey):
        self.registry = registry
        self.storage = storage
        self.public_key = public_key

    @staticmethod
    def _action(authorization: dict[str, Any]) -> dict[str, Any]:
        try:
            action = authorization["payload"]["action"]
        except (KeyError, TypeError) as exc:
            raise ValueError("authorization is missing payload.action") from exc
        if not isinstance(action, dict):
            raise ValueError("authorization action must be an object")
        return action

    @staticmethod
    def _execution_artifact(action: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
        metadata = action.get("metadata")
        if not isinstance(metadata, dict):
            return None, None
        if isinstance(metadata.get("evm_transaction"), dict):
            return "evm", metadata["evm_transaction"]
        if isinstance(metadata.get("solana_transaction"), str):
            return "solana", {"serialized_transaction": metadata["solana_transaction"]}
        return None, None

    @staticmethod
    def _validate_network_binding(action: dict[str, Any], expected_chain_id: int | None) -> None:
        if expected_chain_id is None:
            return
        _, tx = ExecutionRouter._execution_artifact(action)
        if tx is None or "chain_id" not in tx:
            return
        actual_chain_id = tx.get("chain_id")
        if actual_chain_id != expected_chain_id:
            raise ValueError(
                f"EVM chain_id mismatch: network={action.get('network')} "
                f"expected={expected_chain_id} actual={actual_chain_id}"
            )

    def _adapter(self, authorization: dict[str, Any]) -> ExecutionAdapter:
        action = self._action(authorization)
        network = action.get("network")
        if not isinstance(network, str) or not network.strip():
            raise UnsupportedNetworkError("authorized action has no network")

        family, _ = self._execution_artifact(action)

        try:
            descriptor = self.registry.resolve(network)
        except UnsupportedNetworkError:
            descriptor = None

        if descriptor is not None:
            if family is None:
                return ExecutionGate(self.storage, self.public_key)
            if descriptor.family != family:
                raise ValueError(
                    f"execution family mismatch: network={descriptor.family} artifact={family}"
                )
            adapter = self.registry.adapter(network, self.storage, self.public_key)
            self._validate_network_binding(action, descriptor.chain_id)
            return adapter

        metadata = action.get("metadata")
        network_family = metadata.get("network_family") if isinstance(metadata, dict) else None
        if network_family == "evm" and family == "evm":
            tx = metadata.get("evm_transaction")
            chain_id = tx.get("chain_id") if isinstance(tx, dict) else None
            if isinstance(chain_id, int) and chain_id > 0:
                evm = self.registry.resolve_evm_chain(chain_id, name=network)
                self._validate_network_binding(action, evm.chain_id)
                return EVMExecutionAdapter(self.storage, self.public_key)

        if family is None:
            raise UnsupportedNetworkError(f"unsupported execution network: {network}")

        raise UnsupportedNetworkError(f"unsupported execution network: {network}")

    def consume(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        try:
            return self._adapter(authorization).consume(authorization)
        except (KeyError, TypeError, ValueError, UnsupportedNetworkError) as exc:
            return False, str(exc)

    def execute(self, authorization: dict[str, Any], broadcaster: Callable[[dict[str, Any]], Any]) -> Any:
        return self._adapter(authorization).execute(authorization, broadcaster)
