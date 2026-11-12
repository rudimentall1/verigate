"""Transaction preparation and on-chain verification for Verigate Arc Authority Registry.

The operator-controlled issuer signer submits registration. The agent-controlled
EVM executor submits one-time consumption and the payment. The API never receives
or stores either EVM private key.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any

from Crypto.Hash import keccak

from enforcement.evm_rpc import EvmRpcClient, EvmRpcError

ARC_CHAIN_ID = 5042
DEFAULT_REGISTRY = "0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D"
DEFAULT_EXECUTOR = "0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C"

OWNER_SELECTOR = "0x8da5cb5b"
REGISTER_SELECTOR = "0xb267748a"
CONSUME_SELECTOR = "0xbad56b75"
GET_AUTHORIZATION_SELECTOR = "0x215a973e"

REGISTERED_EVENT = "0x8c01e0448f1fba237a495cb1a83dd24d1bb4b496ec1cd15c82b1130bea6b2110"
CONSUMED_EVENT = "0xc808a06a8c1f6acae09e23ef9e49a8992381e788e5bd3908c48c900aa43dd564"

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_HEX32_RE = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")


class ArcAuthorityRegistryError(ValueError):
    """Arc authority registry verification or transaction construction failed."""


def _address(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ADDRESS_RE.fullmatch(value):
        raise ArcAuthorityRegistryError(f"{field} must be a 20-byte EVM address")
    return value.lower()


def _bytes32(value: str, field: str) -> str:
    if not isinstance(value, str) or not _HEX32_RE.fullmatch(value):
        raise ArcAuthorityRegistryError(f"{field} must be bytes32")
    return value.removeprefix("0x").lower()


def _word(value: int) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value >= 2**256:
        raise ArcAuthorityRegistryError("ABI integer is outside uint256 range")
    return format(value, "064x")


def _address_word(value: str) -> str:
    return _address(value, "address")[2:].rjust(64, "0")


def _topic_address(value: str) -> str:
    return "0x" + _address_word(value)


def _function_selector(signature: str) -> str:
    hasher = keccak.new(digest_bits=256)
    hasher.update(signature.encode("ascii"))
    return "0x" + hasher.hexdigest()[:8]


ISSUER_SELECTOR = _function_selector("issuers(address)")


class ArcAuthorityRegistry:
    def __init__(
        self,
        rpc: EvmRpcClient | None = None,
        *,
        contract_address: str | None = None,
        issuer_address: str | None = None,
        executor_address: str | None = None,
        expected_code_hash: str | None = None,
    ):
        self.contract_address = _address(
            contract_address
            or os.environ.get("VERIGATE_ARC_REGISTRY_ADDRESS", DEFAULT_REGISTRY),
            "registry address",
        )
        # The issuer is the operator-controlled account allowed to register
        # authorizations. The executor is taken from each signed payment
        # intent and is the agent-controlled account allowed to consume it.
        self.issuer_address = _address(
            issuer_address
            or os.environ.get("VERIGATE_ARC_ISSUER_ADDRESS")
            or executor_address
            or os.environ.get("VERIGATE_ARC_EXECUTOR_ADDRESS", DEFAULT_EXECUTOR),
            "issuer address",
        )
        # Compatibility alias for older callers and deployment configuration.
        self.executor_address = self.issuer_address
        self.expected_code_hash = (
            expected_code_hash or os.environ.get("VERIGATE_ARC_REGISTRY_CODE_HASH", "")
        ).lower()
        endpoint = os.environ.get("VERIGATE_ARC_RPC_URL", "https://rpc.mainnet.arc.io")
        self.rpc = rpc or EvmRpcClient(endpoint, timeout_seconds=15)

    def _authorization_values(
        self,
        authorization: dict,
        *,
        require_unexpired: bool = True,
    ) -> tuple[str, str, int]:
        if not isinstance(authorization, dict) or not isinstance(authorization.get("payload"), dict):
            raise ArcAuthorityRegistryError("execution authorization is required")

        payload = authorization["payload"]
        authorization_id = _bytes32(payload.get("authorization_id"), "authorization_id")
        valid_until = payload.get("expires_at")

        if isinstance(valid_until, bool) or not isinstance(valid_until, int):
            raise ArcAuthorityRegistryError("authorization expires_at must be an integer")
        if valid_until < 0 or valid_until >= 2**64:
            raise ArcAuthorityRegistryError("authorization expiry is outside uint64 range")
        if require_unexpired and valid_until <= int(time.time()):
            raise ArcAuthorityRegistryError("execution authorization has expired")
        signature = authorization.get("signature")
        algorithm = authorization.get("algorithm")
        if algorithm != "Ed25519" or not isinstance(signature, str) or not signature:
            raise ArcAuthorityRegistryError(
                "execution authorization must carry an Ed25519 signature"
            )
        # Hash the signed envelope by its signature bytes rather than re-serializing
        # JSON across languages. Python and JavaScript stringify integral floats
        # differently (e.g. 1.0 vs 1), which would otherwise produce divergent
        # Registry intent hashes for the same valid authorization.
        hash_input = (
            f"verigate.arc.authority.registry:v2:{ARC_CHAIN_ID}:"
            f"{self.contract_address.lower()}:{algorithm}:{signature}"
        ).encode("ascii")
        intent_hash = hashlib.sha256(hash_input).hexdigest()
        return authorization_id, intent_hash, valid_until

    def verify_deployment(self) -> dict:
        try:
            chain_id = self.rpc.chain_id()
            if chain_id != ARC_CHAIN_ID:
                raise ArcAuthorityRegistryError(
                    f"Arc chain ID mismatch: expected {ARC_CHAIN_ID}, received {chain_id}"
                )

            code = self.rpc.get_code(self.contract_address)
            if code in {"0x", "0x0", "0x00"}:
                raise ArcAuthorityRegistryError("Verigate registry has no deployed bytecode")
            if not re.fullmatch(r"0x[0-9a-f]{64}", self.expected_code_hash):
                raise ArcAuthorityRegistryError(
                    "VERIGATE_ARC_REGISTRY_CODE_HASH must contain the independently verified runtime bytecode hash"
                )
            try:
                hasher = keccak.new(digest_bits=256)
                hasher.update(bytes.fromhex(code.removeprefix("0x")))
                actual_code_hash = "0x" + hasher.hexdigest()
            except (TypeError, ValueError) as exc:
                raise ArcAuthorityRegistryError("Arc registry bytecode is malformed") from exc
            if actual_code_hash != self.expected_code_hash:
                raise ArcAuthorityRegistryError(
                    f"Arc registry runtime bytecode hash mismatch: expected {self.expected_code_hash}, received {actual_code_hash}"
                )

            owner_result = self.rpc.eth_call(self.contract_address, OWNER_SELECTOR)
            if len(owner_result) < 66:
                raise ArcAuthorityRegistryError("registry owner() returned invalid data")

            owner = _address("0x" + owner_result[-40:], "on-chain owner")

            # The registration signer may be the owner or a separately
            # enabled issuer installed by the owner. Do not conflate the two.
            issuer_result = self.rpc.eth_call(
                self.contract_address,
                ISSUER_SELECTOR + _address_word(self.issuer_address),
            )
            if not isinstance(issuer_result, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", issuer_result):
                raise ArcAuthorityRegistryError("Registry issuers() returned invalid data")
            if int(issuer_result, 16) != 1:
                raise ArcAuthorityRegistryError(
                    "configured Arc issuer is not an enabled Registry issuer"
                )

            return {
                "verified": True,
                "chain_id": chain_id,
                "contract_address": self.contract_address,
                "owner": owner,
                "issuer": self.issuer_address,
                "issuer_enabled": True,
                "runtime_code_hash": actual_code_hash,
            }
        except EvmRpcError as exc:
            raise ArcAuthorityRegistryError(f"Arc registry RPC verification failed: {exc}") from exc

    def _authorization_executor(self, authorization: dict) -> str:
        """Resolve the agent EVM executor from the signed payment envelope."""
        try:
            transaction = authorization["payload"]["action"]["metadata"]["evm_transaction"]
            sender = transaction["from"]
        except (KeyError, TypeError) as exc:
            raise ArcAuthorityRegistryError(
                "signed Arc authorization is missing its EVM executor address"
            ) from exc
        return _address(sender, "signed Arc executor")

    def _transaction(self, data: str, *, from_address: str | None = None) -> dict:
        return {
            "chainId": hex(ARC_CHAIN_ID),
            "from": _address(from_address or self.issuer_address, "transaction sender"),
            "to": self.contract_address,
            "data": data,
            "value": "0x0",
        }

    def prepare_registration_transaction(self, authorization: dict) -> dict:
        authorization_id, intent_hash, valid_until = self._authorization_values(authorization)
        executor = self._authorization_executor(authorization)
        data = (
            REGISTER_SELECTOR
            + authorization_id
            + intent_hash
            + _address_word(executor)
            + _word(valid_until)
        )
        return {
            "contract_address": self.contract_address,
            "issuer": self.issuer_address,
            "executor": executor,
            "authorization_id": "0x" + authorization_id,
            "intent_hash": "0x" + intent_hash,
            "valid_until": valid_until,
            "registration_transaction": self._transaction(data, from_address=self.issuer_address),
        }

    def _authorization_state(self, authorization_id: str) -> dict:
        try:
            raw = self.rpc.eth_call(
                self.contract_address,
                GET_AUTHORIZATION_SELECTOR + authorization_id,
            )
        except EvmRpcError as exc:
            raise ArcAuthorityRegistryError(f"getAuthorization RPC call failed: {exc}") from exc

        encoded = raw[2:]
        if len(encoded) < 64 * 6:
            raise ArcAuthorityRegistryError("getAuthorization returned incomplete ABI data")

        words = [encoded[i * 64:(i + 1) * 64] for i in range(6)]
        return {
            "intent_hash": "0x" + words[0].lower(),
            "executor": _address("0x" + words[1][-40:], "stored executor"),
            "valid_until": int(words[2], 16),
            "registered_at": int(words[3], 16),
            "consumed": bool(int(words[4], 16)),
            "revoked": bool(int(words[5], 16)),
        }

    def _confirmed_receipt(
        self,
        transaction_hash: str,
        expected_calldata: str,
        *,
        expected_sender: str | None = None,
    ) -> dict:
        if not isinstance(transaction_hash, str) or not _TX_RE.fullmatch(transaction_hash):
            raise ArcAuthorityRegistryError("transaction hash must be a 32-byte 0x-prefixed hash")

        try:
            receipt = self.rpc.get_transaction_receipt(transaction_hash)
        except EvmRpcError as exc:
            raise ArcAuthorityRegistryError(f"transaction receipt lookup failed: {exc}") from exc

        if receipt is None:
            raise ArcAuthorityRegistryError("transaction is not mined yet")

        try:
            transaction = self.rpc.get_transaction_by_hash(transaction_hash)
        except (EvmRpcError, AttributeError) as exc:
            raise ArcAuthorityRegistryError(
                f"transaction lookup failed; refusing unverified confirmation: {exc}"
            ) from exc

        if transaction is None:
            raise ArcAuthorityRegistryError("mined transaction details are unavailable")

        tx_hash = transaction.get("hash")
        if not isinstance(tx_hash, str) or tx_hash.lower() != transaction_hash.lower():
            raise ArcAuthorityRegistryError("transaction hash does not match RPC response")

        try:
            tx_chain_id = int(transaction.get("chainId"), 16) if isinstance(transaction.get("chainId"), str) else int(transaction.get("chainId"))
            tx_value = int(transaction.get("value", "0x0"), 16) if isinstance(transaction.get("value"), str) else int(transaction.get("value", 0))
        except (TypeError, ValueError):
            raise ArcAuthorityRegistryError("transaction chainId or value is invalid")

        tx_input = transaction.get("input", transaction.get("data", ""))
        if tx_chain_id != ARC_CHAIN_ID:
            raise ArcAuthorityRegistryError("transaction was not sent on Arc Mainnet")
        if _address(transaction.get("to", ""), "transaction destination") != self.contract_address:
            raise ArcAuthorityRegistryError("transaction destination is not the configured registry")
        sender = _address(expected_sender or self.issuer_address, "expected transaction sender")
        if _address(transaction.get("from", ""), "transaction sender") != sender:
            raise ArcAuthorityRegistryError("transaction sender does not match the expected issuer or executor")
        if not isinstance(tx_input, str) or tx_input.lower() != expected_calldata.lower():
            raise ArcAuthorityRegistryError("transaction calldata does not match the expected registry operation")
        if tx_value != 0:
            raise ArcAuthorityRegistryError("registry transaction must not transfer native value")

        receipt_hash = receipt.get("transactionHash")
        if not isinstance(receipt_hash, str) or receipt_hash.lower() != transaction_hash.lower():
            raise ArcAuthorityRegistryError("receipt transaction hash does not match requested hash")

        status = receipt.get("status")
        if status not in ("0x1", 1, "1"):
            raise ArcAuthorityRegistryError("transaction receipt is not successful")

        if _address(receipt.get("to", ""), "receipt destination") != self.contract_address:
            raise ArcAuthorityRegistryError("transaction was not sent to the Verigate registry")

        if _address(receipt.get("from", ""), "receipt sender") != sender:
            raise ArcAuthorityRegistryError("receipt sender does not match the expected issuer or executor")

        if not receipt.get("blockNumber"):
            raise ArcAuthorityRegistryError("confirmed transaction has no block number")

        return receipt

    def _verify_inclusion_before_expiry(
        self,
        receipt: dict,
        valid_until: int,
        valid_from: int | None = None,
    ) -> int:
        block_number = receipt.get("blockNumber")
        if (
            not isinstance(block_number, str)
            or not block_number.startswith("0x")
            or len(block_number) <= 2
        ):
            raise ArcAuthorityRegistryError(
                "confirmed transaction has an invalid inclusion block number"
            )

        try:
            block_number_int = int(block_number, 16)
            block = self.rpc.get_block_by_number(block_number_int)
        except (EvmRpcError, AttributeError, TypeError, ValueError) as exc:
            raise ArcAuthorityRegistryError(
                f"could not verify transaction inclusion block: {exc}"
            ) from exc

        if not isinstance(block, dict):
            raise ArcAuthorityRegistryError(
                "transaction inclusion block is unavailable"
            )

        block_number_from_rpc = block.get("number")
        if (
            not isinstance(block_number_from_rpc, str)
            or block_number_from_rpc.lower() != block_number.lower()
        ):
            raise ArcAuthorityRegistryError(
                "RPC returned a different inclusion block"
            )

        receipt_block_hash = receipt.get("blockHash")
        block_hash = block.get("hash")
        if (
            not isinstance(receipt_block_hash, str)
            or not re.fullmatch(r"0x[0-9a-fA-F]{64}", receipt_block_hash)
            or not isinstance(block_hash, str)
            or not re.fullmatch(r"0x[0-9a-fA-F]{64}", block_hash)
            or block_hash.lower() != receipt_block_hash.lower()
        ):
            raise ArcAuthorityRegistryError(
                "receipt block hash does not match canonical block"
            )

        # Arc uses deterministic finality. Do not add an arbitrary confirmation
        # count: require the inclusion block to be at or below the RPC's
        # finalized head, then retain the exact block-hash comparison above.
        try:
            finalized = self.rpc.get_block_by_tag("finalized")
        except (EvmRpcError, AttributeError) as exc:
            raise ArcAuthorityRegistryError(
                f"Arc finalized block lookup failed; refusing confirmation: {exc}"
            ) from exc
        if not isinstance(finalized, dict):
            raise ArcAuthorityRegistryError("Arc finalized block is unavailable")
        finalized_number = finalized.get("number")
        try:
            if not isinstance(finalized_number, str) or not finalized_number.startswith("0x"):
                raise ValueError("invalid finalized block number")
            finalized_height = int(finalized_number, 16)
        except (TypeError, ValueError) as exc:
            raise ArcAuthorityRegistryError("Arc finalized block number is invalid") from exc
        if finalized_height < block_number_int:
            raise ArcAuthorityRegistryError(
                "transaction inclusion block is not yet finalized by Arc"
            )
        if finalized_height == block_number_int:
            finalized_hash = finalized.get("hash")
            if not isinstance(finalized_hash, str) or finalized_hash.lower() != receipt_block_hash.lower():
                raise ArcAuthorityRegistryError(
                    "Arc finalized block hash does not match transaction inclusion"
                )

        timestamp = block.get("timestamp")
        try:
            if isinstance(timestamp, bool):
                raise ValueError("boolean timestamp")
            if isinstance(timestamp, str):
                if not timestamp.startswith("0x"):
                    raise ValueError("timestamp is not hexadecimal")
                block_timestamp = int(timestamp, 16)
            elif isinstance(timestamp, int):
                block_timestamp = timestamp
            else:
                raise ValueError("unsupported timestamp type")
        except (TypeError, ValueError) as exc:
            raise ArcAuthorityRegistryError(
                "inclusion block has an invalid timestamp"
            ) from exc

        if valid_from is not None and block_timestamp < valid_from:
            raise ArcAuthorityRegistryError(
                "transaction was included before authorization issuance"
            )

        if block_timestamp >= valid_until:
            raise ArcAuthorityRegistryError(
                "transaction was included at or after authorization expiry"
            )

        return block_timestamp

    def registration_verification_time(
        self,
        authorization: dict,
        transaction_hash: str,
    ) -> int:
        """Return the verified canonical timestamp of the registration transaction."""
        self.verify_deployment()

        authorization_id, intent_hash, valid_until = self._authorization_values(
            authorization,
            require_unexpired=False,
        )
        payload = authorization["payload"]
        issued_at = payload.get("issued_at")

        if isinstance(issued_at, bool) or not isinstance(issued_at, int):
            raise ArcAuthorityRegistryError(
                "authorization issued_at must be an integer"
            )
        if issued_at < 0 or issued_at >= valid_until:
            raise ArcAuthorityRegistryError(
                "authorization issuance time is invalid"
            )

        executor = self._authorization_executor(authorization)
        registration_data = (
            REGISTER_SELECTOR
            + authorization_id
            + intent_hash
            + _address_word(executor)
            + _word(valid_until)
        )
        receipt = self._confirmed_receipt(
            transaction_hash, registration_data, expected_sender=self.issuer_address
        )

        return self._verify_inclusion_before_expiry(
            receipt,
            valid_until,
            valid_from=issued_at,
        )

    def _find_event(
        self,
        receipt: dict,
        event_signature: str,
        authorization_id: str,
        intent_hash: str,
        executor_address: str,
    ) -> dict:
        expected = [
            event_signature.lower(),
            "0x" + authorization_id,
            "0x" + intent_hash,
            _topic_address(executor_address),
        ]

        for log in receipt.get("logs", []):
            if _address(log.get("address", ""), "event emitter") != self.contract_address:
                continue
            topics = [str(x).lower() for x in log.get("topics", [])]
            if (
                len(topics) >= 4
                and topics[0] == event_signature.lower()
                and topics[1:4] == expected[1:4]
            ):
                return log

        raise ArcAuthorityRegistryError("expected Verigate registry event is missing from transaction receipt")

    def confirm_registration(self, authorization: dict, transaction_hash: str) -> dict:
        self.verify_deployment()
        authorization_id, intent_hash, valid_until = self._authorization_values(
            authorization, require_unexpired=False
        )
        executor = self._authorization_executor(authorization)
        registration_data = REGISTER_SELECTOR + authorization_id + intent_hash + _address_word(executor) + _word(valid_until)
        receipt = self._confirmed_receipt(
            transaction_hash, registration_data, expected_sender=self.issuer_address
        )
        issued_at = authorization["payload"].get("issued_at")
        if isinstance(issued_at, bool) or not isinstance(issued_at, int):
            raise ArcAuthorityRegistryError(
                "authorization issued_at must be an integer"
            )
        self._verify_inclusion_before_expiry(
            receipt, valid_until, valid_from=issued_at
        )
        log = self._find_event(
            receipt, REGISTERED_EVENT, authorization_id, intent_hash, executor
        )

        event_data = log.get("data", "0x")[2:]
        if len(event_data) < 128:
            raise ArcAuthorityRegistryError("AuthorizationRegistered event has incomplete data")

        event_expiry = int(event_data[:64], 16)
        event_issuer = _address("0x" + event_data[64:128][-40:], "event issuer")
        if event_expiry != valid_until or event_issuer != self.issuer_address:
            raise ArcAuthorityRegistryError("registration event does not match the signed authorization")

        state = self._authorization_state(authorization_id)
        if (
            state["intent_hash"] != "0x" + intent_hash
            or state["executor"] != executor
            or state["valid_until"] != valid_until
            or state["registered_at"] == 0
            or state["revoked"]
        ):
            raise ArcAuthorityRegistryError("on-chain authorization state does not match the signed authorization")

        consume_data = CONSUME_SELECTOR + authorization_id + intent_hash
        return {
            "registered": True,
            "contract_address": self.contract_address,
            "issuer": self.issuer_address,
            "executor": executor,
            "authorization_id": "0x" + authorization_id,
            "intent_hash": "0x" + intent_hash,
            "transaction_ref": transaction_hash,
            "block_ref": receipt["blockNumber"],
            "consume_transaction": self._transaction(consume_data, from_address=executor),
        }

    def confirm_consumption(self, authorization: dict, transaction_hash: str) -> dict:
        self.verify_deployment()
        authorization_id, intent_hash, valid_until = self._authorization_values(
            authorization, require_unexpired=False
        )
        executor = self._authorization_executor(authorization)
        consume_data = CONSUME_SELECTOR + authorization_id + intent_hash
        receipt = self._confirmed_receipt(
            transaction_hash, consume_data, expected_sender=executor
        )
        issued_at = authorization["payload"].get("issued_at")
        if isinstance(issued_at, bool) or not isinstance(issued_at, int):
            raise ArcAuthorityRegistryError(
                "authorization issued_at must be an integer"
            )
        block_timestamp = self._verify_inclusion_before_expiry(
            receipt, valid_until, valid_from=issued_at
        )
        self._find_event(
            receipt, CONSUMED_EVENT, authorization_id, intent_hash, executor
        )

        state = self._authorization_state(authorization_id)
        if (
            state["intent_hash"] != "0x" + intent_hash
            or state["executor"] != executor
            or state["valid_until"] != valid_until
            or not state["consumed"]
            or state["revoked"]
        ):
            raise ArcAuthorityRegistryError("on-chain authorization is not confirmed as consumed")

        return {
            "consumed": True,
            "contract_address": self.contract_address,
            "executor": executor,
            "authorization_id": "0x" + authorization_id,
            "intent_hash": "0x" + intent_hash,
            "transaction_ref": transaction_hash,
            "block_ref": receipt["blockNumber"],
            "block_timestamp": block_timestamp,
        }
