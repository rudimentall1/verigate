"""Strict parser for the deliberately narrow Solana native-transfer envelope.

Only legacy transactions containing one signed System Program transfer are
accepted. Versioned messages, address lookup tables, extra instructions and
other programs fail closed until their semantics are explicitly implemented.
"""
from __future__ import annotations

import base64
import struct
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


_SYSTEM_PROGRAM = bytes(32)
_LAMPORTS_PER_SOL = Decimal(1_000_000_000)
_MAX_TRANSACTION_BYTES = 1_232
_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


class SolanaTransactionError(ValueError):
    """A Solana transaction is malformed or does not match its authorization."""


@dataclass(frozen=True)
class ParsedSolanaTransfer:
    sender: str
    recipient: str
    lamports: int
    signature: str


def _b58encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = _ALPHABET[remainder] + encoded
    zeroes = len(raw) - len(raw.lstrip(bytes([0])))
    return ("1" * zeroes) + encoded


def _b58decode(value: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise SolanaTransactionError("missing Solana address")
    number = 0
    try:
        for char in value:
            number = number * 58 + _ALPHABET.index(char)
    except ValueError as exc:
        raise SolanaTransactionError("invalid base58 Solana address") from exc
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    zeroes = len(value) - len(value.lstrip("1"))
    decoded = bytes([0]) * zeroes + raw
    if len(decoded) != 32 or _b58encode(decoded) != value:
        raise SolanaTransactionError("Solana address must encode exactly 32 bytes")
    return decoded


def _read_shortvec(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    start = offset
    for _ in range(3):
        if offset >= len(data):
            raise SolanaTransactionError("truncated Solana compact-u16")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            if value > 0xFFFF:
                raise SolanaTransactionError("Solana compact-u16 overflow")
            # Reject non-canonical encodings.
            encoded = bytearray()
            remaining = value
            while True:
                part = remaining & 0x7F
                remaining >>= 7
                encoded.append(part | (0x80 if remaining else 0))
                if not remaining:
                    break
            if data[start:offset] != bytes(encoded):
                raise SolanaTransactionError("non-canonical Solana compact-u16")
            return value, offset
        shift += 7
    raise SolanaTransactionError("invalid Solana compact-u16")


def _expected_lamports(action: dict[str, Any]) -> int:
    exact = action.get("amount_exact")
    amount = exact if exact is not None else action.get("amount")
    if amount is None:
        raise SolanaTransactionError("authorized SOL transfer is missing amount")
    try:
        sol = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise SolanaTransactionError("authorized SOL amount is invalid") from exc
    if not sol.is_finite() or sol <= 0:
        raise SolanaTransactionError("authorized SOL amount must be positive and finite")
    lamports = sol * _LAMPORTS_PER_SOL
    if lamports != lamports.to_integral_value():
        raise SolanaTransactionError("authorized SOL amount has sub-lamport precision")
    return int(lamports)


def parse_authorized_native_transfer(action: dict[str, Any]) -> ParsedSolanaTransfer:
    """Parse, cryptographically verify, and bind a legacy SOL transfer to action."""
    if action.get("network") != "solana":
        raise SolanaTransactionError("authorized action network must be solana")
    if action.get("action_type") != "native.transfer":
        raise SolanaTransactionError("only native.transfer is supported by this Solana adapter")
    if action.get("asset") != "SOL":
        raise SolanaTransactionError("only native SOL transfers are supported")
    metadata = action.get("metadata")
    if not isinstance(metadata, dict):
        raise SolanaTransactionError("authorized action is missing metadata")
    raw = metadata.get("solana_transaction")
    if not isinstance(raw, str) or not raw:
        raise SolanaTransactionError("authorized action is missing solana_transaction")
    try:
        wire = base64.b64decode(raw, validate=True)
    except (ValueError, TypeError) as exc:
        raise SolanaTransactionError("invalid Solana transaction encoding") from exc
    if not wire or len(wire) > _MAX_TRANSACTION_BYTES:
        raise SolanaTransactionError("Solana transaction must be between 1 and 1232 bytes")

    signature_count, offset = _read_shortvec(wire, 0)
    if signature_count != 1 or offset + 64 > len(wire):
        raise SolanaTransactionError("exactly one transaction signature is required")
    signature = wire[offset:offset + 64]
    offset += 64
    message = wire[offset:]
    if len(message) < 3 or message[0] & 0x80:
        raise SolanaTransactionError("only legacy Solana transactions are supported")

    required_signatures, readonly_signed, readonly_unsigned = message[:3]
    cursor = 3
    account_count, cursor = _read_shortvec(message, cursor)
    if account_count != 3 or required_signatures != 1:
        raise SolanaTransactionError("native transfer must contain exactly three accounts and one signer")
    if readonly_signed != 0 or readonly_unsigned != 1:
        raise SolanaTransactionError("unexpected Solana account mutability header")
    end_keys = cursor + account_count * 32
    if end_keys + 32 > len(message):
        raise SolanaTransactionError("truncated Solana account keys or blockhash")
    keys = [message[cursor + i * 32:cursor + (i + 1) * 32] for i in range(account_count)]
    cursor = end_keys
    if len(set(keys)) != 3 or keys[2] != _SYSTEM_PROGRAM:
        raise SolanaTransactionError("unexpected or duplicate native-transfer account keys")
    recent_blockhash = message[cursor:cursor + 32]
    if len(recent_blockhash) != 32 or recent_blockhash == bytes(32):
        raise SolanaTransactionError("invalid recent blockhash")
    cursor += 32

    instruction_count, cursor = _read_shortvec(message, cursor)
    if instruction_count != 1:
        raise SolanaTransactionError("exactly one System Program instruction is required")
    if cursor >= len(message):
        raise SolanaTransactionError("truncated Solana instruction")
    program_index = message[cursor]
    cursor += 1
    account_indices_count, cursor = _read_shortvec(message, cursor)
    if account_indices_count != 2 or cursor + 2 > len(message):
        raise SolanaTransactionError("native transfer must reference exactly sender and recipient")
    account_indices = message[cursor:cursor + 2]
    cursor += 2
    data_length, cursor = _read_shortvec(message, cursor)
    if data_length != 12 or cursor + data_length != len(message):
        raise SolanaTransactionError("invalid System Program transfer instruction data")
    instruction_data = message[cursor:cursor + data_length]
    if program_index != 2 or account_indices != bytes([0, 1]):
        raise SolanaTransactionError("transaction instruction is not a direct sender-to-recipient transfer")
    opcode, lamports = struct.unpack("<IQ", instruction_data)
    if opcode != 2 or lamports <= 0:
        raise SolanaTransactionError("only positive System Program Transfer instructions are supported")

    try:
        Ed25519PublicKey.from_public_bytes(keys[0]).verify(signature, message)
    except (InvalidSignature, ValueError) as exc:
        raise SolanaTransactionError("invalid sender Ed25519 transaction signature") from exc

    sender = _b58encode(keys[0])
    recipient = _b58encode(keys[1])
    expected_sender = metadata.get("solana_sender")
    if not isinstance(expected_sender, str) or not expected_sender:
        raise SolanaTransactionError("authorized action is missing solana_sender")
    if sender != expected_sender:
        raise SolanaTransactionError("Solana fee payer/sender does not match authorized sender")
    if recipient != action.get("target"):
        raise SolanaTransactionError("Solana recipient does not match authorized target")
    declared_destination = metadata.get("destination")
    if declared_destination is not None and declared_destination != recipient:
        raise SolanaTransactionError("Solana destination metadata does not match transaction recipient")
    if lamports != _expected_lamports(action):
        raise SolanaTransactionError("Solana transfer amount does not match authorized amount")

    return ParsedSolanaTransfer(
        sender=sender,
        recipient=recipient,
        lamports=lamports,
        signature=_b58encode(signature),
    )
