"""Deterministic-shape Solana transaction fixtures for security tests."""
from __future__ import annotations

import base64
import struct

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    chars = ""
    while number:
        number, rem = divmod(number, 58)
        chars = _ALPHABET[rem] + chars
    zeroes = len(raw) - len(raw.lstrip(bytes([0])))
    return "1" * zeroes + chars


def raw_public_key(key: Ed25519PrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )


def shortvec(value: int) -> bytes:
    out = bytearray()
    while True:
        part = value & 0x7F
        value >>= 7
        out.append(part | (0x80 if value else 0))
        if not value:
            return bytes(out)


def make_signed_transfer(lamports: int = 1_000_000):
    sender = Ed25519PrivateKey.generate()
    recipient = Ed25519PrivateKey.generate()
    sender_raw = raw_public_key(sender)
    recipient_raw = raw_public_key(recipient)
    sender_address = b58encode(sender_raw)
    recipient_address = b58encode(recipient_raw)

    message = (
        bytes([1, 0, 1])
        + shortvec(3)
        + sender_raw
        + recipient_raw
        + bytes(32)  # System Program
        + bytes([9]) * 32  # nonzero recent blockhash
        + shortvec(1)
        + bytes([2])  # programIdIndex
        + shortvec(2)
        + bytes([0, 1])
        + shortvec(12)
        + struct.pack("<IQ", 2, lamports)
    )
    transaction = shortvec(1) + sender.sign(message) + message
    return base64.b64encode(transaction).decode("ascii"), sender_address, recipient_address
