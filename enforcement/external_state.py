"""Live external-state verifiers used immediately before execution."""
from __future__ import annotations

from typing import Any

from core.external_state import external_state_digest_from_observation
from enforcement.evm_rpc import EvmRpcClient


class EVMExternalStateVerifier:
    """Verify an EVM state binding against live JSON-RPC state.

    Binding format::
        {
          "kind": "evm.state",
          "reference": "chain:address",
          "digest": "<sha256>",
          "chain_id": 1,
          "address": "0x...",
          "block_tag": "latest",
          "storage_slots": ["0x...", ...]
        }

    The digest covers the normalized observation, so a code/storage change
    between authorization and execution fails closed before the broadcaster.
    """

    def __init__(self, rpc: EvmRpcClient):
        self.rpc = rpc

    @staticmethod
    def _address(binding: dict[str, Any]) -> str:
        address = binding.get("address")
        if not isinstance(address, str) or not address.startswith("0x") or len(address) != 42:
            raise ValueError("EVM state binding has invalid address")
        return address

    @staticmethod
    def _slots(binding: dict[str, Any]) -> list[str]:
        slots = binding.get("storage_slots", [])
        if not isinstance(slots, list) or any(not isinstance(slot, str) for slot in slots):
            raise ValueError("EVM state binding has invalid storage_slots")
        return slots

    def __call__(self, binding: dict[str, Any], action: dict[str, Any]) -> tuple[bool, str]:
        try:
            if binding.get("kind") != "evm.state":
                return False, "unsupported EVM state binding kind"
            expected_chain = binding.get("chain_id")
            if not isinstance(expected_chain, int) or expected_chain <= 0:
                return False, "EVM state binding has invalid chain_id"
            actual_chain = self.rpc.chain_id()
            if actual_chain != expected_chain:
                return False, f"chain id changed: expected {expected_chain}, got {actual_chain}"

            address = self._address(binding)
            block_tag = binding.get("block_tag", "latest")
            if not isinstance(block_tag, str) or not block_tag:
                return False, "EVM state binding has invalid block_tag"
            slots = self._slots(binding)
            observation = {
                "kind": "evm.state",
                "chain_id": actual_chain,
                "address": address.lower(),
                "block_tag": block_tag,
                "code": self.rpc.get_code(address, block_tag).lower(),
                "storage": {
                    slot.lower(): self.rpc.get_storage_at(address, slot, block_tag).lower()
                    for slot in sorted(slots)
                },
            }
            digest = external_state_digest_from_observation(observation)
            expected_digest = binding.get("digest")
            if digest != expected_digest:
                return False, "EVM state digest changed"
            return True, "EVM state matches authorization"
        except Exception as exc:
            return False, f"EVM state verification failed: {exc}"
