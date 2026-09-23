"""Universal execution router for Verigate."""
from __future__ import annotations

import hashlib
import json

from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from attest.receipt import ExecutionReceipt, sign_execution_receipt

from core.authority_state import DynamicAuthorityService
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

    def __init__(self, registry: NetworkRegistry, storage: Storage, public_key: Ed25519PublicKey, private_key: Ed25519PrivateKey | None = None):
        self.registry = registry
        self.storage = storage
        self.public_key = public_key
        self.private_key = private_key

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


    @staticmethod
    def _transaction_ref(result: Any) -> str | None:
        if isinstance(result, str) and result:
            return result
        if isinstance(result, dict):
            for key in ("transaction_hash", "tx_hash", "signature"):
                value = result.get(key)
                if isinstance(value, str) and value:
                    return value
        return None

    def execute_with_receipt(
        self,
        authorization: dict[str, Any],
        broadcaster: Callable[[dict[str, Any]], Any],
        *,
        executor: str = "verigate",
    ) -> ExecutionReceipt:
        """Broadcast once and persist a signed SUBMITTED or FAILED receipt.

        A failed broadcast still consumes the one-time authorization. Retrying
        requires a fresh authorization.
        """
        if self.private_key is None:
            raise ValueError("execution receipt signing key is required")

        existing = self.storage.execution_receipt_by_authorization(authorization["payload"]["authorization_id"])
        if existing is not None:
            return ExecutionReceipt(
                payload=existing["payload"],
                signature=existing["signature"],
                algorithm=existing.get("algorithm", "Ed25519"),
            )

        try:
            result = self._adapter(authorization).execute(authorization, broadcaster)
            transaction_ref = self._transaction_ref(result)
            if not transaction_ref:
                raise ValueError("broadcaster returned no transaction reference")
            receipt = sign_execution_receipt(
                authorization,
                status="SUBMITTED",
                transaction_ref=transaction_ref,
                executor=executor,
                private_key=self.private_key,
            )
        except Exception as exc:
            receipt = sign_execution_receipt(
                authorization,
                status="FAILED",
                transaction_ref=None,
                executor=executor,
                private_key=self.private_key,
                error=str(exc),
            )

        self.storage.record_execution_receipt(receipt.as_dict())
        capability_id = receipt.payload.get("capability_id")
        if capability_id and receipt.payload["status"] == "FAILED":
            DynamicAuthorityService(self.storage).record_event(
                agent_id=receipt.payload["agent_id"],
                capability_id=capability_id,
                identity_id=receipt.payload.get("identity_id"),
                event_type="EXECUTION_FAILED",
                evidence_ref=receipt.payload["receipt_id"],
            )
        return receipt

    @staticmethod
    def _receipt_digest(receipt: dict[str, Any]) -> str:
        canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def confirm_execution_receipt(self, receipt: dict[str, Any], confirmation: dict[str, Any], *, executor: str = "verigate") -> ExecutionReceipt | None:
        if self.private_key is None:
            raise ValueError("execution receipt signing key is required")
        current = receipt["payload"]
        state = confirmation.get("state")
        if state == "PENDING":
            return None
        if current.get("status") != "SUBMITTED":
            return ExecutionReceipt(payload=current, signature=receipt["signature"], algorithm=receipt.get("algorithm", "Ed25519"))
        if state not in {"CONFIRMED", "FAILED"}:
            raise ValueError("invalid confirmation state")
        transaction_ref = confirmation.get("transaction_ref") or current.get("transaction_ref")
        if not transaction_ref:
            raise ValueError("confirmation is missing transaction reference")
        if transaction_ref != current.get("transaction_ref"):
            raise ValueError("confirmation transaction reference mismatch")
        auth = {"payload": {
            "authorization_id": current["authorization_id"],
            "decision_receipt_sha256": current["decision_receipt_sha256"],
            "intent_id": current["intent_id"],
            "agent_id": current["agent_id"],
            "action_sha256": current["action_sha256"],
            "identity_id": current.get("identity_id"),
            "identity_sha256": current.get("identity_sha256"),
            "capability_id": current.get("capability_id"),
            "capability_sha256": current.get("capability_sha256"),
            "authority_state": current.get("authority_state"),
            "authority_state_sha256": current.get("authority_state_sha256"),
            "authority_multiplier": current.get("authority_multiplier"),
            "action": {"network": current.get("network")},
        }}
        updated = sign_execution_receipt(auth, status=state, transaction_ref=transaction_ref, executor=executor, private_key=self.private_key, error=confirmation.get("error"), receipt_id=current["receipt_id"], previous_receipt_sha256=self._receipt_digest(receipt), confirmation_ref=confirmation.get("block_ref") or confirmation.get("slot"), confirmation_data=confirmation)
        payload = dict(updated.payload)
        payload["network"] = current.get("network")
        updated = ExecutionReceipt(payload=payload, signature=updated.signature, algorithm=updated.algorithm)
        self.storage.update_execution_receipt(updated.as_dict())
        capability_id = updated.payload.get("capability_id")
        if capability_id:
            DynamicAuthorityService(self.storage).record_event(
                agent_id=updated.payload["agent_id"],
                capability_id=capability_id,
                identity_id=updated.payload.get("identity_id"),
                event_type=(
                    "EXECUTION_CONFIRMED"
                    if updated.payload["status"] == "CONFIRMED"
                    else "EXECUTION_FAILED"
                ),
                evidence_ref=updated.payload["receipt_id"],
            )
        return updated
