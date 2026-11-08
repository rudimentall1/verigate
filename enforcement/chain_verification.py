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


_ERC20_TRANSFER_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)
_ERC20_TRANSFER_SELECTOR = "0xa9059cbb"


def _quantity(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} is not a valid EVM quantity")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        raw = value.strip()
        try:
            parsed = int(raw, 16) if raw.lower().startswith("0x") else int(raw, 10)
        except ValueError as exc:
            raise ValueError(f"{field} is not a valid EVM quantity") from exc
    else:
        raise ValueError(f"{field} is not a valid EVM quantity")
    if parsed < 0:
        raise ValueError(f"{field} must not be negative")
    return parsed


def _verify_erc20_transfer_log(
    expected_to: str,
    expected_input: str,
    transaction_from: str,
    receipt: dict[str, Any],
) -> None:
    """Require a matching ERC-20 Transfer event for transfer(address,uint256)."""
    if not expected_input.lower().startswith(_ERC20_TRANSFER_SELECTOR):
        return
    if len(expected_input) != 138:
        raise ValueError("authorized ERC-20 transfer calldata has an invalid length")

    recipient_word = expected_input[10:74].lower()
    amount_word = expected_input[74:138].lower()
    recipient = "0x" + recipient_word[-40:]
    amount = int(amount_word, 16)
    sender_topic = "0x" + transaction_from[2:].lower().rjust(64, "0")

    for log in receipt.get("logs") or []:
        if not isinstance(log, dict):
            continue
        topics = log.get("topics")
        if not isinstance(topics, list) or len(topics) < 3:
            continue
        if str(log.get("address", "")).lower() != expected_to.lower():
            continue
        if str(topics[0]).lower() != _ERC20_TRANSFER_TOPIC:
            continue
        if str(topics[1]).lower() != sender_topic:
            continue
        if str(topics[2]).lower() != ("0x" + recipient_word):
            continue
        if _quantity(log.get("data"), "Transfer event amount") == amount:
            return

    raise ValueError(
        f"confirmed ERC-20 transaction has no matching Transfer event "
        f"for {transaction_from} -> {recipient}"
    )


class EVMChainVerifier(EffectVerifier):
    verifier_type = "CHAIN_VERIFIER_EVM"
    evidence_kind = "CHAIN_RECEIPT"

    def __init__(self, *, expected_sender: str, min_confirmations: int):
        if (
            not isinstance(expected_sender, str)
            or len(expected_sender) != 42
            or not expected_sender.startswith("0x")
            or any(char not in "0123456789abcdefABCDEF" for char in expected_sender[2:])
        ):
            raise ValueError("expected_sender must be a valid enrolled EVM address")
        if (
            isinstance(min_confirmations, bool)
            or not isinstance(min_confirmations, int)
            or min_confirmations < 1
        ):
            raise ValueError("min_confirmations must be a positive integer")
        # These values are trusted verifier configuration, not per-request inputs.
        self.expected_sender = expected_sender.lower()
        self.min_confirmations = min_confirmations

    def verify_receipt(
        self,
        authorization: dict[str, Any],
        rpc: EvmRpcClient,
        *,
        transaction_hash: str,
        evidence_ref: str | None = None,
        observed_at: float | None = None,
    ) -> ObservedEffect:
        """Verify an effect against a verifier-pinned wallet and finality policy.

        The verifier instance must be constructed from a trusted wallet-enrollment
        registry or equivalent governed configuration. Do not construct it from
        an address copied from the transaction or supplied by an untrusted caller.
        """
        payload = authorization.get("payload") if isinstance(authorization, dict) else None
        action = payload.get("action") if isinstance(payload, dict) else None
        metadata = action.get("metadata") if isinstance(action, dict) else None
        expected = metadata.get("evm_transaction") if isinstance(metadata, dict) else None
        if not isinstance(expected, dict):
            raise ValueError("authorization has no signed EVM transaction envelope")

        expected_chain_id = _quantity(expected.get("chain_id"), "authorized chain_id")
        expected_to = expected.get("to")
        expected_input = expected.get("data")
        expected_value = _quantity(expected.get("value_wei"), "authorized value_wei")
        if not isinstance(expected_to, str) or not expected_to.startswith("0x") or len(expected_to) != 42:
            raise ValueError("authorized EVM transaction has an invalid destination")
        if not isinstance(expected_input, str) or not expected_input.startswith("0x"):
            raise ValueError("authorized EVM transaction has invalid calldata")

        actual_chain_id = rpc.chain_id()
        if actual_chain_id != expected_chain_id:
            raise ValueError(
                f"EVM RPC chain id {actual_chain_id} does not match authorized chain id {expected_chain_id}"
            )

        result = rpc.confirm_transaction(transaction_hash)
        receipt_state = result["state"]
        state = receipt_state
        receipt = result.get("receipt")
        transaction = None
        confirmation_count = 0
        canonical_block_hash = None
        receipt_block_number = None

        if receipt is not None:
            transaction = rpc.get_transaction_by_hash(transaction_hash)
            if transaction is None:
                raise ValueError("mined EVM receipt has no corresponding transaction")

            if str(transaction.get("hash", "")).lower() != transaction_hash.lower():
                raise ValueError("EVM transaction hash does not match the requested hash")
            if str(transaction.get("to", "")).lower() != expected_to.lower():
                raise ValueError("observed EVM transaction destination does not match authorization")
            actual_input = transaction.get("input", transaction.get("data"))
            if not isinstance(actual_input, str) or actual_input.lower() != expected_input.lower():
                raise ValueError("observed EVM transaction calldata does not match authorization")
            if _quantity(transaction.get("value"), "observed transaction value") != expected_value:
                raise ValueError("observed EVM transaction value does not match authorization")

            transaction_chain_id = transaction.get("chainId")
            if transaction_chain_id is None:
                raise ValueError("observed EVM transaction is missing chainId")
            if _quantity(
                transaction_chain_id, "observed transaction chainId"
            ) != expected_chain_id:
                raise ValueError("observed EVM transaction chain id does not match authorization")

            actual_sender = transaction.get("from")
            if not isinstance(actual_sender, str) or actual_sender.lower() != self.expected_sender:
                raise ValueError("observed EVM transaction sender does not match the enrolled wallet")

            if not isinstance(receipt, dict):
                raise ValueError("mined EVM transaction has no receipt")
            if str(receipt.get("transactionHash", "")).lower() != transaction_hash.lower():
                raise ValueError("EVM receipt transaction hash does not match the requested hash")
            if str(receipt.get("to", "")).lower() != expected_to.lower():
                raise ValueError("EVM receipt destination does not match authorization")
            if str(receipt.get("from", "")).lower() != actual_sender.lower():
                raise ValueError("EVM receipt sender does not match transaction sender")

            receipt_block_number = _quantity(receipt.get("blockNumber"), "receipt blockNumber")
            transaction_block_number = transaction.get("blockNumber")
            if transaction_block_number is None or _quantity(
                transaction_block_number, "transaction blockNumber"
            ) != receipt_block_number:
                raise ValueError("EVM transaction block number does not match receipt")
            receipt_block_hash = receipt.get("blockHash")
            transaction_block_hash = transaction.get("blockHash")
            if (
                not isinstance(receipt_block_hash, str)
                or not isinstance(transaction_block_hash, str)
                or receipt_block_hash.lower() != transaction_block_hash.lower()
            ):
                raise ValueError("EVM transaction block hash does not match receipt")

            canonical_block = rpc.get_block_by_number(receipt_block_number)
            if canonical_block is None:
                state = "PENDING"
            else:
                canonical_block_hash = canonical_block["hash"]
                if canonical_block_hash.lower() != receipt_block_hash.lower():
                    raise ValueError("EVM receipt block hash is not canonical")
                head_number = rpc.block_number()
                if head_number < receipt_block_number:
                    raise ValueError("EVM head is behind the mined receipt block")
                confirmation_count = head_number - receipt_block_number + 1
                if confirmation_count < self.min_confirmations:
                    state = "PENDING"

            if state == "CONFIRMED":
                _verify_erc20_transfer_log(
                    expected_to,
                    expected_input,
                    actual_sender,
                    receipt,
                )

        if state == "PENDING":
            status = "UNKNOWN"
        elif state == "CONFIRMED":
            status = "SUCCEEDED"
        else:
            status = "FAILED"

        observation = {
            "network": "EVM",
            "chain_id": actual_chain_id,
            "transaction_hash": transaction_hash,
            "state": state,
            "block_ref": result.get("block_ref"),
            "block_hash": result.get("block_hash"),
            "receipt_block_number": receipt_block_number,
            "canonical_block_hash": canonical_block_hash,
            "confirmations": confirmation_count,
            "required_confirmations": self.min_confirmations,
            "transaction_to": transaction.get("to") if transaction else None,
            "transaction_from": transaction.get("from") if transaction else None,
            "transaction_input_sha256": digest(transaction.get("input", transaction.get("data"))) if transaction else None,
            "transaction_value_wei": str(_quantity(transaction.get("value"), "observed transaction value")) if transaction else None,
            "receipt_sha256": digest(receipt) if receipt is not None else None,
        }
        return self.observe(
            authorization,
            observation=observation,
            evidence_ref=evidence_ref or f"evm:{rpc.endpoint}:{transaction_hash}",
            result=receipt or result,
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
