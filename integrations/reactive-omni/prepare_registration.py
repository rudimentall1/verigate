#!/usr/bin/env python3
"""Prepare a Base Sepolia registration transaction from a verified Verigate ALLOW.

This tool never receives an EVM private key and never broadcasts a transaction.
It validates the complete API response (signed decision receipt + signed
execution authorization), checks the deployed origin hub and issuer on RPC,
then prints a wallet-signable transaction request.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Crypto.Hash import keccak

from attest.keys import load_public_key
from attest.receipt import verify_execution_authorization, verify_receipt
from enforcement.evm_rpc import EvmRpcClient, EvmRpcError

BASE_SEPOLIA_CHAIN_ID = 84532
UNICHAIN_SEPOLIA_CHAIN_ID = 1301
DEFAULT_EXPECTED_NETWORK = "unichain-sepolia"
DEFAULT_EXPECTED_ASSET = "ETH"

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_BYTES32_RE = re.compile(r"^(?:0x)?[0-9a-fA-F]{64}$")


class PreparationError(ValueError):
    """A Verigate artifact or origin hub does not satisfy bridge requirements."""


def _address(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _ADDRESS_RE.fullmatch(value):
        raise PreparationError(f"{field} must be a 20-byte EVM address")
    return value.lower()


def _bytes32(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _BYTES32_RE.fullmatch(value):
        raise PreparationError(f"{field} must be a 32-byte hex value")
    return value.removeprefix("0x").lower()


def _word(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value >= 2**256:
        raise PreparationError("ABI integer is outside uint256 range")
    return format(value, "064x")


def _address_word(value: str) -> str:
    return value.removeprefix("0x").rjust(64, "0")


def _selector(signature: str) -> str:
    hasher = keccak.new(digest_bits=256)
    hasher.update(signature.encode("ascii"))
    return hasher.hexdigest()[:8]


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _to_wei(amount_exact: Any) -> int:
    if not isinstance(amount_exact, str) or not amount_exact:
        raise PreparationError("action.amount_exact is required; floating-point amount is not accepted")
    try:
        amount = Decimal(amount_exact)
    except InvalidOperation as exc:
        raise PreparationError("action.amount_exact is not a valid decimal") from exc
    if not amount.is_finite() or amount <= 0:
        raise PreparationError("action.amount_exact must be finite and greater than zero")
    wei = amount * Decimal(10**18)
    if wei != wei.to_integral_value():
        raise PreparationError("amount_exact has more precision than native-token wei")
    return int(wei)


def verify_artifact(
    artifact: dict[str, Any],
    public_key_path: str,
    expected_network: str,
    expected_asset: str,
) -> dict[str, Any]:
    if not isinstance(artifact, dict):
        raise PreparationError("input must be a JSON object")
    receipt = artifact.get("decision_receipt")
    authorization = artifact.get("execution_authorization")
    if not isinstance(receipt, dict) or not isinstance(authorization, dict):
        raise PreparationError(
            "input must contain decision_receipt and execution_authorization from /v1/actions/authorize"
        )

    public_key = load_public_key(public_key_path)
    valid_receipt, receipt_reason = verify_receipt(receipt, public_key)
    if not valid_receipt:
        raise PreparationError(f"decision receipt verification failed: {receipt_reason}")

    receipt_payload = receipt.get("payload")
    auth_payload = authorization.get("payload")
    if not isinstance(receipt_payload, dict) or not isinstance(auth_payload, dict):
        raise PreparationError("signed artifact payloads are malformed")
    if receipt_payload.get("decision", {}).get("decision") != "ALLOW":
        raise PreparationError("only an ALLOW decision can be registered")
    if receipt_payload.get("intent", {}).get("intent_id") != auth_payload.get("intent_id"):
        raise PreparationError("execution authorization does not reference this decision receipt intent")

    expected_receipt_hash = hashlib.sha256(
        _canonical(receipt_payload) + receipt["signature"].encode("ascii")
    ).hexdigest()
    if auth_payload.get("decision_receipt_sha256") != expected_receipt_hash:
        raise PreparationError("execution authorization is not bound to the supplied decision receipt")

    valid_authorization, authorization_reason = verify_execution_authorization(
        authorization,
        public_key,
    )
    if not valid_authorization:
        raise PreparationError(
            f"execution authorization verification failed: {authorization_reason}"
        )

    action = auth_payload.get("action")
    if not isinstance(action, dict):
        raise PreparationError("execution authorization action is missing")
    if action.get("action_type") != "payment":
        raise PreparationError("only action_type=payment is supported by this adapter")
    if action.get("network") != expected_network:
        raise PreparationError(
            f"action network must equal {expected_network!r}; received {action.get('network')!r}"
        )
    if action.get("asset") != expected_asset:
        raise PreparationError(
            f"action asset must equal {expected_asset!r}; received {action.get('asset')!r}"
        )

    recipient = _address(action.get("target"), "action.target")
    amount_wei = _to_wei(action.get("amount_exact"))

    authorization_id = _bytes32(auth_payload.get("authorization_id"), "authorization_id")
    action_hash = _bytes32(auth_payload.get("action_sha256"), "action_sha256")
    policy_hash = _bytes32(auth_payload.get("policy_sha256"), "policy_sha256")
    receipt_hash = _bytes32(auth_payload.get("decision_receipt_sha256"), "decision_receipt_sha256")

    expires_at = auth_payload.get("expires_at")
    if isinstance(expires_at, bool) or not isinstance(expires_at, int):
        raise PreparationError("expires_at must be an integer Unix timestamp")
    if expires_at <= __import__("time").time():
        raise PreparationError("execution authorization is already expired")
    if expires_at >= 2**64:
        raise PreparationError("expires_at is outside uint64 range")

    return {
        "authorization_id": authorization_id,
        "verigate_action_hash": action_hash,
        "policy_sha256": policy_hash,
        "decision_receipt_sha256": receipt_hash,
        "recipient": recipient,
        "amount_wei": amount_wei,
        "expires_at": expires_at,
        "intent_id": auth_payload.get("intent_id"),
        "agent_id": auth_payload.get("agent_id"),
        "action": action,
    }


def verify_origin_hub(rpc_url: str, hub: str, issuer: str) -> None:
    rpc = EvmRpcClient(rpc_url, timeout_seconds=15)
    try:
        chain_id = rpc.chain_id()
        if chain_id != BASE_SEPOLIA_CHAIN_ID:
            raise PreparationError(
                f"origin RPC chain ID mismatch: expected {BASE_SEPOLIA_CHAIN_ID}, received {chain_id}"
            )
        code = rpc.get_code(hub)
        if not isinstance(code, str) or code in {"0x", "0x0", "0x00"}:
            raise PreparationError("origin hub has no deployed bytecode at the supplied address")

        issuer_selector = "0x" + _selector("issuers(address)")
        issuer_word = _address_word(issuer)
        result = rpc.eth_call(hub, issuer_selector + issuer_word)
        if not isinstance(result, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", result):
            raise PreparationError("origin hub issuers(address) returned invalid data")
        if int(result, 16) != 1:
            raise PreparationError("the selected EVM issuer is not enabled on the origin hub")
    except EvmRpcError as exc:
        raise PreparationError(f"origin hub RPC verification failed: {exc}") from exc


def build_registration_transaction(
    values: dict[str, Any],
    hub: str,
    issuer: str,
    destination_receiver: str,
) -> dict[str, Any]:
    selector = _selector(
        "registerAuthorization(bytes32,bytes32,bytes32,bytes32,uint256,address,address,uint256,uint64)"
    )
    words = [
        values["authorization_id"],
        values["verigate_action_hash"],
        values["policy_sha256"],
        values["decision_receipt_sha256"],
        _word(UNICHAIN_SEPOLIA_CHAIN_ID),
        _address_word(destination_receiver),
        _address_word(values["recipient"]),
        _word(values["amount_wei"]),
        _word(values["expires_at"]),
    ]
    return {
        "chainId": hex(BASE_SEPOLIA_CHAIN_ID),
        "from": issuer,
        "to": hub,
        "value": "0x0",
        "data": "0x" + selector + "".join(words),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a Verigate ALLOW artifact and prepare a Base Sepolia issuer transaction."
    )
    parser.add_argument("artifact", help="JSON response from POST /v1/actions/authorize")
    parser.add_argument("--public-key", required=True, help="Verigate Ed25519 issuer public key PEM")
    parser.add_argument("--origin-hub", required=True, help="Deployed VerigateOriginAuthorizationHub")
    parser.add_argument("--issuer", required=True, help="EVM wallet address enabled as an origin hub issuer")
    parser.add_argument("--destination-receiver", required=True, help="Deployed Unichain Sepolia callback receiver")
    parser.add_argument("--rpc-url", default=None, help="Base Sepolia RPC; defaults to VERIGATE_REACTIVE_ORIGIN_RPC_URL")
    parser.add_argument("--expected-network", default=DEFAULT_EXPECTED_NETWORK)
    parser.add_argument("--expected-asset", default=DEFAULT_EXPECTED_ASSET)
    args = parser.parse_args()

    try:
        hub = _address(args.origin_hub, "origin hub")
        issuer = _address(args.issuer, "issuer")
        receiver = _address(args.destination_receiver, "destination receiver")
        rpc_url = args.rpc_url or __import__("os").environ.get("VERIGATE_REACTIVE_ORIGIN_RPC_URL")
        if not rpc_url:
            raise PreparationError("provide --rpc-url or VERIGATE_REACTIVE_ORIGIN_RPC_URL")

        artifact = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
        values = verify_artifact(
            artifact,
            args.public_key,
            args.expected_network,
            args.expected_asset,
        )
        verify_origin_hub(rpc_url, hub, issuer)
        transaction = build_registration_transaction(values, hub, issuer, receiver)

        print(json.dumps({
            "verified": True,
            "status": "WALLET_SIGNATURE_REQUIRED",
            "chain": "Base Sepolia",
            "chain_id": BASE_SEPOLIA_CHAIN_ID,
            "origin_hub": hub,
            "issuer": issuer,
            "destination_chain": "Unichain Sepolia",
            "destination_chain_id": UNICHAIN_SEPOLIA_CHAIN_ID,
            "destination_receiver": receiver,
            "authorization": {
                "authorization_id": "0x" + values["authorization_id"],
                "action_sha256": "0x" + values["verigate_action_hash"],
                "policy_sha256": "0x" + values["policy_sha256"],
                "decision_receipt_sha256": "0x" + values["decision_receipt_sha256"],
                "intent_id": values["intent_id"],
                "agent_id": values["agent_id"],
                "recipient": values["recipient"],
                "amount_wei": str(values["amount_wei"]),
                "expires_at": values["expires_at"],
            },
            "transaction": transaction,
        }, indent=2))
        return 0
    except (PreparationError, OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(json.dumps({"verified": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
