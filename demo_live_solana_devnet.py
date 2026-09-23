#!/usr/bin/env python3
"""Real Verigate execution lifecycle on Solana Devnet.

Creates ephemeral devnet-only keys, requests faucet SOL, signs a tiny SOL
transfer, routes it through Verigate, broadcasts via Solana RPC, and converts
the submitted execution receipt into a confirmed signed receipt.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import struct
import time
from pathlib import Path
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authorization import AuthorizationService
from core.models import ActionIntent, Decision, GuardrailDecision
from core.storage import Storage
from enforcement.monitor import ExecutionMonitor
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter
from enforcement.solana_rpc import SolanaRpcClient


RPC_URL = os.environ.get("VERIGATE_SOLANA_DEVNET_RPC_URL", "https://api.devnet.solana.com")
LAMPORTS_PER_SOL = 1_000_000_000
TRANSFER_LAMPORTS = 1_000_000


def shortvec(value: int) -> bytes:
    if value < 0:
        raise ValueError("shortvec value cannot be negative")
    out = bytearray()
    while True:
        elem = value & 0x7F
        value >>= 7
        if value:
            out.append(elem | 0x80)
        else:
            out.append(elem)
            return bytes(out)


_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58encode(raw: bytes) -> str:
    number = int.from_bytes(raw, "big")
    chars = []
    while number:
        number, remainder = divmod(number, 58)
        chars.append(_ALPHABET[remainder])
    leading_zeroes = len(raw) - len(raw.lstrip(b"\\x00"))
    return "1" * leading_zeroes + "".join(reversed(chars or ["1"]))


def b58decode(value: str) -> bytes:
    number = 0
    for char in value:
        number = number * 58 + _ALPHABET.index(char)
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    leading_ones = len(value) - len(value.lstrip("1"))
    return b"\\x00" * leading_ones + raw


def raw_public_key(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


def load_solana_keypair(path: Path) -> Ed25519PrivateKey:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) not in {32, 64}:
        raise ValueError("Solana keypair JSON must contain 32 or 64 bytes")
    secret = bytes(raw[:32])
    return Ed25519PrivateKey.from_private_bytes(secret)


def sign_system_transfer(
    sender: Ed25519PrivateKey,
    recipient_pubkey: bytes,
    recent_blockhash: str,
    lamports: int,
) -> str:
    sender_pubkey = raw_public_key(sender)
    system_program = bytes(32)

    header = bytes([1, 0, 1])
    account_keys = (
        shortvec(3)
        + sender_pubkey
        + recipient_pubkey
        + system_program
    )
    blockhash = b58decode(recent_blockhash)
    if len(blockhash) != 32:
        raise ValueError("Solana blockhash must decode to 32 bytes")

    instruction_data = struct.pack("<IQ", 2, lamports)
    instruction = (
        bytes([2])
        + shortvec(2)
        + bytes([0, 1])
        + shortvec(len(instruction_data))
        + instruction_data
    )
    message = (
        header
        + account_keys
        + blockhash
        + shortvec(1)
        + instruction
    )
    signature = sender.sign(message)
    transaction = shortvec(1) + signature + message
    return base64.b64encode(transaction).decode("ascii")


def wait_for_confirmed(
    rpc: SolanaRpcClient,
    signature: str,
    timeout_seconds: int = 30,
) -> dict:
    deadline = time.time() + timeout_seconds
    last = None
    while time.time() < deadline:
        last = rpc.confirm_transaction(signature)
        if last["state"] != "PENDING":
            return last
        time.sleep(1)
    return last or {"state": "PENDING", "transaction_ref": signature}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sender-keypair",
        type=Path,
        help="existing Solana CLI keypair JSON for a funded Devnet sender",
    )
    parser.add_argument(
        "--skip-airdrop",
        action="store_true",
        help="do not request faucet SOL; use the supplied funded sender",
    )
    args = parser.parse_args()
    rpc = SolanaRpcClient(RPC_URL)

    with tempfile.TemporaryDirectory(prefix="verigate-live-solana-") as td:
        root = Path(td)
        issuer_private = root / "issuer.key"
        issuer_public = root / "issuer.pub"
        audit_db = root / "audit.db"
        generate_keypair(issuer_private, issuer_public)

        sender = (
            load_solana_keypair(args.sender_keypair)
            if args.sender_keypair
            else Ed25519PrivateKey.generate()
        )
        recipient = Ed25519PrivateKey.generate()
        sender_address = b58encode(raw_public_key(sender))
        recipient_address = b58encode(raw_public_key(recipient))

        print("=" * 62)
        print("VERIGATE | LIVE SOLANA DEVNET EXECUTION")
        print("=" * 62)
        print("RPC:", RPC_URL)
        print("Sender:", sender_address)
        print("Recipient:", recipient_address)

        print()
        if args.skip_airdrop or args.sender_keypair:
            print("1) Using existing funded Devnet sender; faucet skipped.")
        else:
            print("1) Requesting 1 SOL from Devnet faucet...")
            try:
                airdrop_sig = rpc.request_airdrop(sender_address, LAMPORTS_PER_SOL)
                airdrop_state = wait_for_confirmed(rpc, airdrop_sig)
                if airdrop_state["state"] != "CONFIRMED":
                    raise RuntimeError(f"Devnet faucet did not confirm: {airdrop_state}")
                print("Airdrop:", airdrop_state["state"], airdrop_sig)
            except Exception as exc:
                raise RuntimeError(
                    "Devnet faucet failed. Re-run with --sender-keypair <funded-keypair.json> "
                    "--skip-airdrop after funding the sender on Devnet."
                ) from exc

        balance = rpc.get_balance(sender_address)
        print("Sender balance:", balance / LAMPORTS_PER_SOL, "SOL")
        required = TRANSFER_LAMPORTS + 100_000
        if balance < required:
            raise RuntimeError(
                f"Sender needs at least {required / LAMPORTS_PER_SOL:.6f} SOL; "
                "fund the Devnet sender first."
            )

        latest = rpc.get_latest_blockhash()
        raw_tx = sign_system_transfer(
            sender,
            raw_public_key(recipient),
            latest["blockhash"],
            TRANSFER_LAMPORTS,
        )

        intent = ActionIntent(
            agent_id="verigate-live-solana",
            action_type="native.transfer",
            target=recipient_address,
            amount=TRANSFER_LAMPORTS / LAMPORTS_PER_SOL,
            asset="SOL",
            network="solana",
            metadata={
                "solana_transaction": raw_tx,
                "network_environment": "devnet",
                "destination": recipient_address,
            },
        )
        decision = GuardrailDecision(
            intent_id=intent.intent_id,
            agent_id=intent.agent_id,
            decision=Decision.ALLOW,
            matched_rules=(),
        )

        auth = AuthorizationService().issue(
            intent,
            decision,
            "live-solana-devnet-policy",
            load_private_key(issuer_private),
            nonce=intent.intent_id,
        )["execution_authorization"]

        storage = Storage(audit_db)
        router = ExecutionRouter(
            NetworkRegistry(),
            storage,
            load_public_key(issuer_public),
            load_private_key(issuer_private),
        )

        print()
        print("2) Verigate authorization")
        print("Decision: ALLOW")
        print("Execution authorization:", "ISSUED")

        try:
            print()
            print("3) ExecutionRouter -> Solana RPC broadcast")
            submitted = router.execute_with_receipt(
                auth,
                lambda tx: rpc.send_transaction(tx["serialized_transaction"]),
            )
            print("Receipt status:", submitted.payload["status"])
            print("Transaction:", submitted.payload["transaction_ref"])

            print()
            print("4) ExecutionMonitor -> getSignatureStatuses")
            monitor = ExecutionMonitor({"solana": rpc})
            confirmation = wait_for_confirmed(
                rpc,
                submitted.payload["transaction_ref"],
                timeout_seconds=30,
            )
            print("RPC state:", confirmation["state"])

            confirmed = router.confirm_execution_receipt(
                submitted.as_dict(),
                confirmation,
            )
            if confirmed is None:
                raise RuntimeError(
                    "transaction remained PENDING; no terminal receipt was created"
                )

            print("Receipt status:", confirmed.payload["status"])
            print("Slot:", confirmed.payload.get("confirmation_ref"))
            print()
            print("Explorer:")
            print(
                "https://explorer.solana.com/tx/"
                + submitted.payload["transaction_ref"]
                + "?cluster=devnet"
            )
            print()
            print("RESULT: REAL DEVNET BROADCAST -> SUBMITTED -> CONFIRMED")
        finally:
            storage.close()

        print("=" * 62)


if __name__ == "__main__":
    main()
