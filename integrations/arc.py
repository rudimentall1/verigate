"""Arc mainnet integration for Verigate.

This module contains Arc-specific network checks and USDC ERC-20 transfer
encoding. It does not hold wallet keys or broadcast transactions: the
connected wallet remains the signer, and Verigate's signed authorization
must be consumed before the client broadcasts.
"""
from __future__ import annotations

import os
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from enforcement.evm_rpc import EvmRpcClient, EvmRpcError

ARC_CHAIN = "arc"
ARC_CHAIN_ID = 5042
ARC_RPC_URL = "https://rpc.mainnet.arc.io"
ARC_EXPLORER_URL = "https://explorer.arc.io"
ARC_USDC_ADDRESS = "0x3600000000000000000000000000000000000000"
ARC_USDC_ERC20_DECIMALS = 6
ARC_NATIVE_GAS_ASSET = "USDC"
ARC_NATIVE_GAS_DECIMALS = 18
ARC_USDC_DECIMALS_SELECTOR = "0x313ce567"
ERC20_TRANSFER_SELECTOR = "0xa9059cbb"
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_UINT256_MAX = (1 << 256) - 1


class ArcIntegrationError(ValueError):
    """Raised when Arc network or payment parameters fail validation."""


def _address(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ADDRESS_RE.fullmatch(value):
        raise ArcIntegrationError(f"{field} must be a 20-byte EVM address")
    return value.lower()


def usdc_to_base_units(amount: str | int | float | Decimal) -> int:
    """Convert a human USDC amount to the Arc ERC-20's 6-decimal units."""
    try:
        value = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise ArcIntegrationError("USDC amount must be a valid decimal") from exc
    if not value.is_finite() or value <= 0:
        raise ArcIntegrationError("USDC amount must be finite and positive")
    scaled = value * (10 ** ARC_USDC_ERC20_DECIMALS)
    if scaled != scaled.to_integral_value():
        raise ArcIntegrationError("Arc USDC ERC-20 amounts support at most 6 decimal places")
    units = int(scaled)
    if units > _UINT256_MAX:
        raise ArcIntegrationError("USDC amount exceeds uint256")
    return units


def build_usdc_transfer_calldata(
    recipient: str,
    amount: str | int | float | Decimal,
) -> str:
    """Encode ERC-20 transfer(address,uint256) for Arc USDC."""
    normalized_recipient = _address(recipient, "recipient")
    units = usdc_to_base_units(amount)
    recipient_word = normalized_recipient[2:].rjust(64, "0")
    amount_word = format(units, "064x")
    return ERC20_TRANSFER_SELECTOR + recipient_word + amount_word


def build_usdc_transfer_transaction(
    sender: str,
    recipient: str,
    amount: str | int | float | Decimal,
) -> dict[str, int | str]:
    """Build a wallet-signable Arc mainnet transaction envelope.

    USDC ERC-20 transfer amounts use 6 decimals. The native Arc gas asset is
    also USDC, but its native-value denomination uses 18 decimals; therefore
    an ERC-20 transfer has value_wei=0 and does not put the payment amount
    into the native transaction value.
    """
    normalized_sender = _address(sender, "sender")
    normalized_recipient = _address(recipient, "recipient")
    return {
        "chain_id": ARC_CHAIN_ID,
        "from": normalized_sender,
        "to": ARC_USDC_ADDRESS,
        "value_wei": 0,
        "data": build_usdc_transfer_calldata(normalized_recipient, amount),
    }


def arc_payment_metadata(
    sender: str,
    recipient: str,
    amount: str | int | float | Decimal,
) -> dict:
    """Return the exact EVM envelope to include in a signed ActionIntent."""
    return {
        "network_family": "evm",
        "evm_transaction": build_usdc_transfer_transaction(sender, recipient, amount),
        "arc": {
            "chain_id": ARC_CHAIN_ID,
            "asset": "USDC",
            "token_address": ARC_USDC_ADDRESS,
            "token_decimals": ARC_USDC_ERC20_DECIMALS,
        },
    }


def validate_arc_usdc_transfer(
    transaction: dict,
    *,
    sender: str,
    recipient: str,
    amount: str | int | float | Decimal,
) -> None:
    """Fail closed unless the signed transaction is the exact Arc USDC transfer."""
    expected = build_usdc_transfer_transaction(sender, recipient, amount)
    if not isinstance(transaction, dict):
        raise ArcIntegrationError("metadata.evm_transaction must be an object")
    for field in ("chain_id", "from", "to", "value_wei", "data"):
        if transaction.get(field) != expected[field]:
            raise ArcIntegrationError(f"Arc USDC transaction {field} does not match the signed payment intent")


class ArcMainnetIntegration:
    """Read-only verifier for Arc mainnet and its canonical USDC ERC-20."""

    def __init__(self, rpc: EvmRpcClient | None = None, rpc_url: str | None = None):
        endpoint = rpc_url or os.environ.get("VERIGATE_ARC_RPC_URL", ARC_RPC_URL)
        self.rpc = rpc or EvmRpcClient(endpoint, timeout_seconds=10)

    def status(self) -> dict:
        chain_id = self.rpc.chain_id()
        if chain_id != ARC_CHAIN_ID:
            raise ArcIntegrationError(
                f"Arc RPC chain ID mismatch: expected {ARC_CHAIN_ID}, received {chain_id}"
            )

        block_number = self.rpc.block_number()
        gas_price_wei = self.rpc.gas_price_wei()
        token_code = self.rpc.get_code(ARC_USDC_ADDRESS)
        if token_code in {"0x", "0x0", "0x00"}:
            raise ArcIntegrationError("canonical Arc USDC contract has no deployed bytecode")

        decimals_hex = self.rpc.eth_call(ARC_USDC_ADDRESS, ARC_USDC_DECIMALS_SELECTOR)
        try:
            token_decimals = int(decimals_hex, 16)
        except (TypeError, ValueError) as exc:
            raise ArcIntegrationError("Arc USDC decimals() returned an invalid value") from exc
        if token_decimals != ARC_USDC_ERC20_DECIMALS:
            raise ArcIntegrationError(
                f"Arc USDC ERC-20 decimals mismatch: expected {ARC_USDC_ERC20_DECIMALS}, received {token_decimals}"
            )

        return {
            "network": ARC_CHAIN,
            "chain_id": chain_id,
            "block_number": block_number,
            "native_gas_asset": ARC_NATIVE_GAS_ASSET,
            "native_gas_decimals": ARC_NATIVE_GAS_DECIMALS,
            "usdc_erc20_address": ARC_USDC_ADDRESS,
            "usdc_erc20_decimals": token_decimals,
            "gas_price_wei": gas_price_wei,
            "gas_price_native_usdc": str(Decimal(gas_price_wei) / (10 ** ARC_NATIVE_GAS_DECIMALS)),
            "explorer": ARC_EXPLORER_URL,
            "rpc_host": urlsplit(self.rpc.endpoint).hostname,
            "verified": True,
        }


TRANSFER_EVENT_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
_TX_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")


class ArcPaymentVerificationError(ValueError):
    """Raised when an Arc USDC settlement cannot be independently verified."""


def _rpc_int(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise ArcPaymentVerificationError(f"{field} is invalid")
    try:
        if isinstance(value, int):
            parsed = value
        elif isinstance(value, str) and value.startswith("0x"):
            parsed = int(value, 16)
        else:
            raise ValueError("not an integer or 0x quantity")
    except (TypeError, ValueError) as exc:
        raise ArcPaymentVerificationError(f"{field} is invalid") from exc
    if parsed < 0:
        raise ArcPaymentVerificationError(f"{field} is invalid")
    return parsed


class ArcPaymentSettlementVerifier:
    """Read-only verifier for a wallet-broadcast Arc USDC payment."""

    def __init__(self, rpc: EvmRpcClient | None = None):
        endpoint = os.environ.get("VERIGATE_ARC_RPC_URL", ARC_RPC_URL)
        self.rpc = rpc or EvmRpcClient(endpoint, timeout_seconds=15)

    def confirm_payment(
        self,
        *,
        expected_transaction: dict,
        payment_transaction_hash: str,
        consumption_transaction_hash: str,
    ) -> dict:
        if not isinstance(expected_transaction, dict):
            raise ArcPaymentVerificationError("signed Arc payment transaction is required")
        for field in ("chain_id", "from", "to", "value_wei", "data"):
            if field not in expected_transaction:
                raise ArcPaymentVerificationError(f"signed Arc payment transaction is missing {field}")
        if not _TX_HASH_RE.fullmatch(payment_transaction_hash or ""):
            raise ArcPaymentVerificationError("payment transaction hash must be a 32-byte 0x-prefixed hash")
        if not _TX_HASH_RE.fullmatch(consumption_transaction_hash or ""):
            raise ArcPaymentVerificationError("consumption transaction hash must be a 32-byte 0x-prefixed hash")

        try:
            if self.rpc.chain_id() != ARC_CHAIN_ID:
                raise ArcPaymentVerificationError("RPC is not connected to Arc Mainnet")
            payment_tx = self.rpc.get_transaction_by_hash(payment_transaction_hash)
            payment_receipt = self.rpc.get_transaction_receipt(payment_transaction_hash)
            consumption_tx = self.rpc.get_transaction_by_hash(consumption_transaction_hash)
            consumption_receipt = self.rpc.get_transaction_receipt(consumption_transaction_hash)
        except EvmRpcError as exc:
            raise EvmRpcError(f"Arc transaction lookup failed: {exc}") from exc

        if payment_tx is None or payment_receipt is None:
            raise ArcPaymentVerificationError("Arc payment transaction is not mined")
        if str(payment_tx.get("hash", "")).lower() != payment_transaction_hash.lower():
            raise ArcPaymentVerificationError("payment transaction hash mismatch")
        if consumption_tx is None or consumption_receipt is None:
            raise ArcPaymentVerificationError("Arc Registry consumption transaction is unavailable")
        if str(consumption_tx.get("hash", "")).lower() != consumption_transaction_hash.lower():
            raise ArcPaymentVerificationError("Registry consumption transaction hash mismatch")
        if str(consumption_receipt.get("transactionHash", "")).lower() != consumption_transaction_hash.lower():
            raise ArcPaymentVerificationError("Registry consumption receipt hash mismatch")
        if consumption_receipt.get("status") not in ("0x1", 1, "1"):
            raise ArcPaymentVerificationError("Arc Registry consumption transaction did not succeed")

        expected_chain_id = _rpc_int(expected_transaction["chain_id"], "signed chain ID")
        expected_sender = _address(expected_transaction["from"], "signed payment sender")
        expected_token = _address(expected_transaction["to"], "signed payment token")
        expected_value = _rpc_int(expected_transaction["value_wei"], "signed native value")
        expected_data = expected_transaction["data"]
        if expected_chain_id != ARC_CHAIN_ID or expected_token != ARC_USDC_ADDRESS or expected_value != 0:
            raise ArcPaymentVerificationError("signed transaction is not a canonical Arc USDC ERC-20 transfer")
        if not isinstance(expected_data, str) or not re.fullmatch(r"0x[a-fA-F0-9]{136}", expected_data):
            raise ArcPaymentVerificationError("signed Arc USDC transfer calldata is malformed")
        if expected_data[:10].lower() != ERC20_TRANSFER_SELECTOR:
            raise ArcPaymentVerificationError("signed Arc payment is not ERC-20 transfer(address,uint256)")

        calldata = expected_data[10:]
        expected_recipient = _address("0x" + calldata[24:64], "signed payment recipient")
        expected_amount = int(calldata[64:128], 16)
        if expected_amount <= 0:
            raise ArcPaymentVerificationError("signed Arc USDC transfer amount must be positive")

        try:
            tx_chain_id = _rpc_int(payment_tx.get("chainId"), "payment chain ID")
            tx_value = _rpc_int(payment_tx.get("value", "0x0"), "payment native value")
            tx_index = _rpc_int(payment_receipt.get("transactionIndex"), "payment transaction index")
            consume_index = _rpc_int(consumption_receipt.get("transactionIndex"), "consumption transaction index")
            payment_block_number = _rpc_int(payment_receipt.get("blockNumber"), "payment block number")
            consume_block_number = _rpc_int(consumption_receipt.get("blockNumber"), "consumption block number")
            tx_block_number = _rpc_int(payment_tx.get("blockNumber"), "payment transaction block number")
            tx_index_from_transaction = _rpc_int(payment_tx.get("transactionIndex"), "payment transaction index")
        except ArcPaymentVerificationError:
            raise

        tx_data = payment_tx.get("input", payment_tx.get("data", ""))
        if tx_block_number != payment_block_number or tx_index_from_transaction != tx_index:
            raise ArcPaymentVerificationError("payment transaction and receipt inclusion coordinates differ")
        if tx_chain_id != ARC_CHAIN_ID:
            raise ArcPaymentVerificationError("payment transaction was not sent on Arc Mainnet")
        if _address(payment_tx.get("from", ""), "payment transaction sender") != expected_sender:
            raise ArcPaymentVerificationError("payment transaction sender does not match the signed authorization")
        if _address(payment_tx.get("to", ""), "payment transaction token") != expected_token:
            raise ArcPaymentVerificationError("payment transaction destination is not canonical Arc USDC")
        if tx_value != 0 or not isinstance(tx_data, str) or tx_data.lower() != expected_data.lower():
            raise ArcPaymentVerificationError("payment transaction does not match the signed USDC transfer")

        if payment_receipt.get("status") not in ("0x1", 1, "1"):
            raise ArcPaymentVerificationError("Arc USDC payment transaction did not succeed")
        if str(payment_receipt.get("transactionHash", "")).lower() != payment_transaction_hash.lower():
            raise ArcPaymentVerificationError("payment receipt transaction hash mismatch")
        if _address(payment_receipt.get("from", ""), "payment receipt sender") != expected_sender:
            raise ArcPaymentVerificationError("payment receipt sender mismatch")
        if _address(payment_receipt.get("to", ""), "payment receipt destination") != expected_token:
            raise ArcPaymentVerificationError("payment receipt destination mismatch")
        if payment_block_number < consume_block_number or (
            payment_block_number == consume_block_number and tx_index <= consume_index
        ):
            raise ArcPaymentVerificationError("USDC payment was not ordered after Registry authorization consumption")

        try:
            payment_block = self.rpc.get_block_by_number(payment_block_number)
            finalized_block = self.rpc.get_block_by_tag("finalized")
        except EvmRpcError as exc:
            raise EvmRpcError(f"Arc finality lookup failed: {exc}") from exc
        except AttributeError as exc:
            raise ArcPaymentVerificationError(f"Arc finality lookup is unavailable: {exc}") from exc
        if not isinstance(payment_block, dict) or not isinstance(finalized_block, dict):
            raise ArcPaymentVerificationError("Arc payment block or finalized head is unavailable")

        payment_block_hash = payment_block.get("hash")
        receipt_block_hash = payment_receipt.get("blockHash")
        transaction_block_hash = payment_tx.get("blockHash")
        if (
            not isinstance(payment_block_hash, str)
            or not _TX_HASH_RE.fullmatch(payment_block_hash)
            or not isinstance(receipt_block_hash, str)
            or not isinstance(transaction_block_hash, str)
            or payment_block_hash.lower() != receipt_block_hash.lower()
            or payment_block_hash.lower() != transaction_block_hash.lower()
        ):
            raise ArcPaymentVerificationError("payment receipt block hash does not match the canonical block")
        finalized_number = _rpc_int(finalized_block.get("number"), "finalized block number")
        if finalized_number < payment_block_number:
            raise ArcPaymentVerificationError("Arc payment inclusion block is not finalized")
        if finalized_number == payment_block_number and str(finalized_block.get("hash", "")).lower() != payment_block_hash.lower():
            raise ArcPaymentVerificationError("Arc finalized block hash does not match the payment block")

        timestamp = _rpc_int(payment_block.get("timestamp"), "payment block timestamp")
        logs = payment_receipt.get("logs")
        if not isinstance(logs, list):
            raise ArcPaymentVerificationError("payment receipt logs are missing")
        sender_topic = "0x" + expected_sender[2:].rjust(64, "0")
        recipient_topic = "0x" + expected_recipient[2:].rjust(64, "0")
        matching_logs = []
        for log in logs:
            if not isinstance(log, dict) or str(log.get("address", "")).lower() != expected_token:
                continue
            topics = log.get("topics")
            data = log.get("data")
            if (
                isinstance(topics, list)
                and len(topics) == 3
                and str(topics[0]).lower() == TRANSFER_EVENT_TOPIC
                and str(topics[1]).lower() == sender_topic
                and str(topics[2]).lower() == recipient_topic
                and isinstance(data, str)
                and re.fullmatch(r"0x[0-9a-fA-F]{64}", data)
                and int(data, 16) == expected_amount
            ):
                matching_logs.append(log)
        if len(matching_logs) != 1:
            raise ArcPaymentVerificationError(
                f"expected exactly one matching canonical USDC Transfer event, found {len(matching_logs)}"
            )

        return {
            "verified": True,
            "chain_id": ARC_CHAIN_ID,
            "token_address": expected_token,
            "token": "USDC",
            "token_decimals": ARC_USDC_ERC20_DECIMALS,
            "sender": expected_sender,
            "recipient": expected_recipient,
            "amount_base_units": str(expected_amount),
            "payment_transaction_hash": payment_transaction_hash.lower(),
            "payment_block_number": payment_block_number,
            "payment_block_hash": payment_block_hash.lower(),
            "payment_block_timestamp": timestamp,
            "payment_transaction_index": tx_index,
            "transfer_log_index": _rpc_int(matching_logs[0].get("logIndex"), "Transfer log index"),
            "consumption_transaction_hash": consumption_transaction_hash.lower(),
            "consumption_block_number": consume_block_number,
            "finalized_block_number": finalized_number,
            "finalized_block_hash": str(finalized_block.get("hash", "")).lower(),
            "explorer_url": f"{ARC_EXPLORER_URL}/tx/{payment_transaction_hash.lower()}",
        }
