"""Independent chain-effect verification adapters.

These adapters observe an already-authorized transaction on the chain. They do
not submit transactions and never grant authority. The returned observation is
suitable for a CHAIN_RECEIPT OutcomeClaim and subsequent attestation.
"""
from __future__ import annotations

from typing import Any

from core.effect_verification import EffectVerifier, ObservedEffect, digest
from enforcement.evm_rpc import EvmRpcClient
from enforcement.solana_rpc import SolanaRpcClient


class EVMChainVerifier(EffectVerifier):
    verifier_type = "CHAIN_VERIFIER_EVM"
    evidence_kind = "CHAIN_RECEIPT"

    def verify_receipt(
        self,
        authorization: dict[str, Any],
        rpc: EvmRpcClient,
        *,
        transaction_hash: str,
        evidence_ref: str | None = None,
        observed_at: float | None = None,
    ) -> ObservedEffect:
        result = rpc.confirm_transaction(transaction_hash)
        state = result["state"]
        if state == "PENDING":
            status = "UNKNOWN"
        elif state == "CONFIRMED":
            status = "SUCCEEDED"
        else:
            status = "FAILED"
        receipt = result.get("receipt") or result
        observation = {
            "network": "EVM",
            "chain_id": rpc.chain_id(),
            "transaction_hash": transaction_hash,
            "state": state,
            "block_ref": result.get("block_ref"),
            "block_hash": result.get("block_hash"),
            "receipt_sha256": digest(receipt),
        }
        return self.observe(
            authorization,
            observation=observation,
            evidence_ref=evidence_ref or f"evm:{rpc.endpoint}:{transaction_hash}",
            result=receipt,
            status=status,
            observed_at=observed_at,
        )


class SolanaChainVerifier(EffectVerifier):
    verifier_type = "CHAIN_VERIFIER_SOLANA"
    evidence_kind = "CHAIN_RECEIPT"

    def verify_signature(
        self,
        authorization: dict[str, Any],
        rpc: SolanaRpcClient,
        *,
        signature: str,
        evidence_ref: str | None = None,
        observed_at: float | None = None,
    ) -> ObservedEffect:
        result = rpc.confirm_transaction(signature)
        state = result["state"]
        status = "UNKNOWN" if state == "PENDING" else ("SUCCEEDED" if state == "CONFIRMED" else "FAILED")
        observation = {
            "network": "SOLANA",
            "transaction_signature": signature,
            "state": state,
            "slot": result.get("slot"),
            "confirmation_status": result.get("confirmation_status"),
            "status_sha256": digest(result.get("status") or result),
        }
        return self.observe(
            authorization,
            observation=observation,
            evidence_ref=evidence_ref or f"solana:{rpc.endpoint}:{signature}",
            result=result.get("status") or result,
            status=status,
            observed_at=observed_at,
        )
