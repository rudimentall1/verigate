"""Universal execution router for Verigate."""
from __future__ import annotations

import hashlib
import json

from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from attest.receipt import (
    ExecutionReceipt,
    sign_execution_receipt,
    verify_execution_authorization,
)

from core.storage import Storage
from core.execution_graph import verify_execution_graph
from core.execution_artifact import verify_execution_artifact
from core.external_state import (
    ExternalStateVerifierRegistry,
    external_state_requirement_for_action,
    validate_external_state_requirement,
    verify_external_state_binding,
)
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

    def __init__(
        self,
        registry: NetworkRegistry,
        storage: Storage,
        public_key: Ed25519PublicKey,
        private_key: Ed25519PrivateKey | None = None,
        generic_adapters: dict[str, ExecutionAdapter] | None = None,
        external_state_verifier: Callable[[dict[str, Any], dict[str, Any]], tuple[bool, str]] | None = None,
        external_state_registry: ExternalStateVerifierRegistry | None = None,
    ):
        self.registry = registry
        self.storage = storage
        self.public_key = public_key
        self.private_key = private_key
        self.generic_adapters = dict(generic_adapters or {})
        self.external_state_verifier = external_state_verifier
        self.external_state_registry = external_state_registry

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
        action_type = action.get("action_type")
        generic = self.generic_adapters.get(action_type)
        if generic is not None:
            return generic
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

    def _verify_authorization(self, authorization: dict[str, Any]) -> None:
        valid, reason = verify_execution_authorization(authorization, self.public_key)
        if not valid:
            raise ValueError(f"execution authorization rejected: {reason}")

    def _verify_external_state(self, authorization: dict[str, Any]) -> None:
        payload = authorization["payload"]
        action = self._action(authorization)
        expected = payload.get("external_state")
        required = bool(payload.get("external_state_required"))
        if not isinstance(expected, dict):
            raise ValueError("execution authorization is missing external state binding")
        verified_binding = expected
        ok, reason = verify_external_state_binding(expected, action)
        if not ok:
            raise ValueError(reason)
        if not expected:
            if required:
                raise ValueError("external state binding required before execution")
            return None
        requirement = payload.get("external_state_requirement")
        if requirement is not None:
            valid, reason = validate_external_state_requirement(requirement)
            if not valid:
                raise ValueError(reason)
            if expected.get("kind") != requirement.get("kind"):
                raise ValueError("external state kind does not satisfy policy requirement")
        if self.external_state_registry is not None:
            ok, reason = self.external_state_registry.verify(expected, action)
        elif self.external_state_verifier is not None:
            ok, reason = self.external_state_verifier(expected, action)
        else:
            raise ValueError("live external state verifier is required before execution")
        if not ok:
            raise ValueError(f"external state drift: {reason}")
        return verified_binding

    def _verify_execution_path(self, authorization: dict[str, Any], adapter: ExecutionAdapter) -> None:
        action = self._action(authorization)
        expected = authorization["payload"].get("execution_graph")
        if not isinstance(expected, dict):
            raise ValueError("execution authorization is missing execution graph binding")
        # Empty graph means this authorization predates optional execution-path
        # policy. When a graph is declared, however, it is mandatory at runtime.
        if not expected:
            return
        actual = {
            "module": adapter.__class__.__module__,
            "hook": adapter.__class__.__name__,
            "router": self.__class__.__name__,
            "target": action.get("target"),
            "enforcement_scope": getattr(adapter, "execution_enforcement_scope", "direct"),
        }
        ok, reason = verify_execution_graph(expected, actual)
        if not ok:
            raise ValueError(reason)
        expected_artifact = authorization["payload"].get("execution_artifact")
        if not isinstance(expected_artifact, dict):
            raise ValueError("execution authorization is missing execution artifact binding")
        ok, reason = verify_execution_artifact(expected_artifact, action)
        if not ok:
            raise ValueError(reason)

    def consume(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        try:
            # The router is itself an execution boundary. Do not trust a
            # protocol adapter (including custom generic adapters) to perform
            # cryptographic verification on our behalf.
            self._verify_authorization(authorization)
            adapter = self._adapter(authorization)
            self._verify_execution_path(authorization, adapter)
            self._verify_external_state(authorization)
            return adapter.consume(authorization)
        except (KeyError, TypeError, ValueError, UnsupportedNetworkError) as exc:
            return False, str(exc)

    def execute(self, authorization: dict[str, Any], broadcaster: Callable[[dict[str, Any]], Any]) -> Any:
        self._verify_authorization(authorization)
        adapter = self._adapter(authorization)
        self._verify_execution_path(authorization, adapter)
        state_required = bool(authorization["payload"].get("external_state_required"))
        external_state = self._verify_external_state(authorization)
        if state_required and external_state:
            bound = getattr(adapter, "execute_bound", None)
            if not callable(bound):
                raise ValueError(
                    "atomic external state enforcement is required for this authorization"
                )
            return bound(authorization, external_state, broadcaster)
        return adapter.execute(authorization, broadcaster)


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
            # Use the same execution boundary as direct execution so required
            # atomic state enforcement cannot be bypassed by receipt generation.
            result = self.execute(authorization, broadcaster)
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
        # ExecutionReceipt is executor evidence only. Dynamic authority changes
        # require an independent OutcomeAttestation, so a local executor cannot
        # promote or demote itself by merely reporting an outcome.
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
            "policy_sha256": current.get("policy_sha256"),
            "signed_policy_version": current.get("signed_policy_version"),
            "policy_version_sha256": current.get("policy_version_sha256"),
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
            "authority_policy_sha256": current.get("authority_policy_sha256"),
            "authority_policy": current.get("authority_policy"),
            "authority_policy_artifact_sha256": current.get("authority_policy_artifact_sha256"),
            "genesis_authority": current.get("genesis_authority"),
            "genesis_authority_sha256": current.get("genesis_authority_sha256"),
            "action": {"network": current.get("network")},
        }}
        updated = sign_execution_receipt(auth, status=state, transaction_ref=transaction_ref, executor=executor, private_key=self.private_key, error=confirmation.get("error"), receipt_id=current["receipt_id"], previous_receipt_sha256=self._receipt_digest(receipt), confirmation_ref=confirmation.get("block_ref") or confirmation.get("slot"), confirmation_data=confirmation)
        payload = dict(updated.payload)
        payload["network"] = current.get("network")
        updated = ExecutionReceipt(payload=payload, signature=updated.signature, algorithm=updated.algorithm)
        self.storage.update_execution_receipt(updated.as_dict())
        # Confirmation updates the execution evidence, but does not by itself
        # change authority. A separate trusted attestor must confirm the effect.
        return updated
