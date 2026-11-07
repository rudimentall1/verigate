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
