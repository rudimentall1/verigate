"""Deterministic recipient-address validation.

No network calls and no oracles: this only answers "is this string a
well-formed address for this network?". A well-formed address does NOT prove
the recipient is safe or legitimate.
"""
from __future__ import annotations

import re

EVM_NETWORKS = frozenset({
    "base", "ethereum", "mainnet", "arbitrum", "optimism", "polygon", "bsc", "bnb",
    "avalanche", "linea", "scroll", "zksync", "gnosis", "celo", "base-sepolia", "sepolia",
})
SOLANA_NETWORKS = frozenset({"solana", "solana-devnet", "solana-testnet"})

_HEX40 = re.compile(r"^0x[0-9a-fA-F]{40}$")
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_MASK = (1 << 64) - 1
_RC = (
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
)
_ROT = (
    (0, 36, 3, 41, 18), (1, 44, 10, 45, 2), (62, 6, 43, 15, 61),
    (28, 55, 25, 21, 56), (27, 20, 39, 8, 14),
)


def _rol(value: int, shift: int) -> int:
    shift %= 64
    return ((value << shift) | (value >> (64 - shift))) & _MASK if shift else value


def _keccak_f(a: list[int]) -> None:
    for rc in _RC:
        c = [a[x] ^ a[x + 5] ^ a[x + 10] ^ a[x + 15] ^ a[x + 20] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rol(c[(x + 1) % 5], 1) for x in range(5)]
        for i in range(25):
            a[i] ^= d[i % 5]
        b = [0] * 25
        for x in range(5):
            for y in range(5):
                b[y + 5 * ((2 * x + 3 * y) % 5)] = _rol(a[x + 5 * y], _ROT[x][y])
        for y in range(5):
            for x in range(5):
                a[x + 5 * y] = b[x + 5 * y] ^ ((~b[(x + 1) % 5 + 5 * y]) & b[(x + 2) % 5 + 5 * y])
        a[0] ^= rc


def keccak256(data: bytes) -> bytes:
    """Keccak-256 as used by Ethereum (not the NIST SHA3-256 padding)."""
    rate = 136
    padded = bytearray(data) + b"\x01"
    while len(padded) % rate:
        padded.append(0)
    padded[-1] |= 0x80
    state = [0] * 25
    for off in range(0, len(padded), rate):
        block = padded[off:off + rate]
        for i in range(rate // 8):
            state[i] ^= int.from_bytes(block[8 * i:8 * i + 8], "little")
        _keccak_f(state)
    return b"".join(state[i].to_bytes(8, "little") for i in range(4))


def _eip55_ok(address: str) -> bool:
    body = address[2:]
    if body == body.lower() or body == body.upper():
        return True  # not mixed case: no checksum is claimed
    digest = keccak256(body.lower().encode("ascii")).hex()
    for i, ch in enumerate(body):
        if ch.isdigit():
            continue
        if (ch.isupper()) != (int(digest[i], 16) >= 8):
            return False
    return True


def _b58_decode(text: str) -> bytes | None:
    n = 0
    for ch in text:
        i = _B58.find(ch)
        if i < 0:
            return None
        n = n * 58 + i
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""
    return b"\x00" * (len(text) - len(text.lstrip("1"))) + raw


def validate_payee(payee: object, network: object) -> str | None:
    """Return a human-readable problem, or None if the recipient is well formed."""
    if not isinstance(payee, str) or not payee.strip():
        return "the recipient is empty"
    if payee != payee.strip() or any(ch.isspace() or ord(ch) < 32 for ch in payee):
        return "the recipient contains whitespace or control characters"
    if len(payee) > 128:
        return "the recipient is too long"
    net = (network if isinstance(network, str) else "").strip().lower()
    if net in EVM_NETWORKS:
        if not _HEX40.match(payee):
            return "not a valid EVM address (expected 0x followed by exactly 40 hexadecimal characters)"
        if int(payee, 16) == 0:
            return "the zero address is not a valid recipient"
        if not _eip55_ok(payee):
            return "the EIP-55 checksum does not match (possible typo)"
        return None
    if net in SOLANA_NETWORKS:
        decoded = _b58_decode(payee)
        if decoded is None or len(decoded) != 32:
            return "not a valid Solana address (expected base58 encoding of 32 bytes)"
        return None
    return None
