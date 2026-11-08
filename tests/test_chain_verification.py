import unittest
import json

from enforcement.chain_verification import EVMChainVerifier, SolanaChainVerifier
from enforcement.evm_rpc import EvmRpcClient
from enforcement.solana_rpc import SolanaRpcClient


class ChainVerificationTest(unittest.TestCase):
    def setUp(self):
        self.tx_hash = "0x" + "1" * 64
        self.token = "0x" + "c" * 40
        self.sender = "0x" + "a" * 40
        self.destination = "0x" + "b" * 40
        self.evm_auth = {
            "payload": {
                "authorization_id": "auth-evm",
                "action_sha256": "a" * 64,
                "action": {
                    "action_type": "evm.transaction",
                    "metadata": {
                        "evm_transaction": {
                            "chain_id": 5050,
                            "to": self.token,
                            "value_wei": 0,
                            "data": "0xdeadbeef",
                        }
                    },
                },
            }
        }
        self.sol_auth = {
            "payload": {
                "authorization_id": "auth-sol",
                "action_sha256": "b" * 64,
                "action": {"action_type": "solana.transaction"},
            }
        }

    def _rpc_transport(
        self,
        *,
        tx_to=None,
        tx_input=None,
        receipt_hash=None,
        logs=None,
        head_block_number="0x1b",
        canonical_block_hash=None,
        transaction_block_hash=None,
        transaction_block_number="0x10",
        transaction_chain_id="0x13ba",
    ):
        def transport(endpoint, payload, headers, timeout):
            req = json.loads(payload)
            if req["method"] == "eth_chainId":
                return json.dumps({"result": "0x13ba"}).encode()
            if req["method"] == "eth_getTransactionByHash":
                return json.dumps({"result": {
                    "hash": self.tx_hash,
                    "from": self.sender,
                    "to": tx_to or self.token,
                    "input": tx_input or "0xdeadbeef",
                    "value": "0x0",
                    "chainId": transaction_chain_id,
                    "blockNumber": transaction_block_number,
                    "blockHash": transaction_block_hash or ("0x" + "b" * 64),
                }}).encode()
            if req["method"] == "eth_getTransactionReceipt":
                return json.dumps({"result": {
                    "transactionHash": receipt_hash or self.tx_hash,
                    "status": "0x1",
                    "blockNumber": "0x10",
                    "blockHash": "0x" + "b" * 64,
                    "from": self.sender,
                    "to": tx_to or self.token,
                    "logs": logs or [],
                }}).encode()
            if req["method"] == "eth_getBlockByNumber":
                return json.dumps({"result": {
                    "number": req["params"][0],
                    "hash": canonical_block_hash or ("0x" + "b" * 64),
                }}).encode()
            if req["method"] == "eth_blockNumber":
                return json.dumps({"result": head_block_number}).encode()
            raise AssertionError(req["method"])
        return transport

    def test_evm_verifier_requires_pinned_wallet_and_confirmation_policy(self):
        with self.assertRaisesRegex(ValueError, "enrolled EVM address"):
            EVMChainVerifier(expected_sender="caller-controlled", min_confirmations=12)
        with self.assertRaisesRegex(ValueError, "positive integer"):
            EVMChainVerifier(expected_sender=self.sender, min_confirmations=0)
        with self.assertRaisesRegex(ValueError, "positive integer"):
            EVMChainVerifier(expected_sender=self.sender, min_confirmations=True)

    def test_evm_receipt_is_bound_to_exact_authorized_transaction(self):
        observed = EVMChainVerifier(expected_sender=self.sender, min_confirmations=12).verify_receipt(
            self.evm_auth,
            EvmRpcClient("http://rpc", transport=self._rpc_transport()),
            transaction_hash=self.tx_hash,
            observed_at=10.0,
        )
        self.assertEqual(observed.effect_status, "SUCCEEDED")
        self.assertEqual(observed.evidence_kind, "CHAIN_RECEIPT")
        self.assertEqual(observed.observation["chain_id"], 5050)
        self.assertEqual(observed.observation["transaction_hash"], self.tx_hash)
        self.assertEqual(observed.observation["transaction_to"], self.token)
        self.assertEqual(observed.observation["transaction_from"], self.sender)
        self.assertEqual(observed.observation["confirmations"], 12)
        self.assertEqual(observed.observation["required_confirmations"], 12)

    def test_evm_receipt_below_confirmation_depth_is_unknown(self):
        rpc = EvmRpcClient(
            "http://rpc",
            transport=self._rpc_transport(head_block_number="0x1a"),
        )
        observed = EVMChainVerifier(expected_sender=self.sender, min_confirmations=12).verify_receipt(
            self.evm_auth,
            rpc,
            transaction_hash=self.tx_hash,
        )
        self.assertEqual(observed.effect_status, "UNKNOWN")
        self.assertEqual(observed.observation["confirmations"], 11)

    def test_evm_noncanonical_receipt_block_is_rejected(self):
        rpc = EvmRpcClient(
            "http://rpc",
            transport=self._rpc_transport(canonical_block_hash="0x" + "c" * 64),
        )
        with self.assertRaisesRegex(ValueError, "block hash is not canonical"):
            EVMChainVerifier(expected_sender=self.sender, min_confirmations=12).verify_receipt(
                self.evm_auth,
                rpc,
                transaction_hash=self.tx_hash,
            )

    def test_evm_transaction_must_include_signed_chain_id(self):
        rpc = EvmRpcClient(
            "http://rpc",
            transport=self._rpc_transport(transaction_chain_id=None),
        )
        with self.assertRaisesRegex(ValueError, "missing chainId"):
            EVMChainVerifier(
                expected_sender=self.sender,
                min_confirmations=12,
            ).verify_receipt(
                self.evm_auth,
                rpc,
                transaction_hash=self.tx_hash,
            )

    def test_evm_sender_must_match_trusted_wallet_enrollment(self):
        rpc = EvmRpcClient("http://rpc", transport=self._rpc_transport())
        with self.assertRaisesRegex(ValueError, "sender does not match the enrolled wallet"):
            EVMChainVerifier(
                expected_sender="0x" + "d" * 40,
                min_confirmations=12,
            ).verify_receipt(
                self.evm_auth,
                rpc,
                transaction_hash=self.tx_hash,
            )

    def test_evm_pending_is_unknown(self):
        def transport(endpoint, payload, headers, timeout):
            req = json.loads(payload)
            if req["method"] == "eth_chainId":
                return json.dumps({"result": "0x13ba"}).encode()
            if req["method"] == "eth_getTransactionReceipt":
                return json.dumps({"result": None}).encode()
            raise AssertionError(req["method"])

        observed = EVMChainVerifier(expected_sender=self.sender, min_confirmations=12).verify_receipt(
            self.evm_auth,
            EvmRpcClient("http://rpc", transport=transport),
            transaction_hash=self.tx_hash,
        )
        self.assertEqual(observed.effect_status, "UNKNOWN")

    def test_successful_but_unrelated_transaction_is_rejected(self):
        unrelated = "0x" + "d" * 40
        rpc = EvmRpcClient(
            "http://rpc",
            transport=self._rpc_transport(tx_to=unrelated, tx_input="0xfeedface"),
        )
        with self.assertRaisesRegex(ValueError, "destination does not match authorization"):
            EVMChainVerifier(expected_sender=self.sender, min_confirmations=12).verify_receipt(
                self.evm_auth,
                rpc,
                transaction_hash=self.tx_hash,
            )

    def test_same_destination_but_different_calldata_is_rejected(self):
        rpc = EvmRpcClient(
            "http://rpc",
            transport=self._rpc_transport(tx_input="0xfeedface"),
        )
        with self.assertRaisesRegex(ValueError, "calldata does not match authorization"):
            EVMChainVerifier(expected_sender=self.sender, min_confirmations=12).verify_receipt(
                self.evm_auth,
                rpc,
                transaction_hash=self.tx_hash,
            )

    def test_receipt_hash_must_match_requested_transaction(self):
        rpc = EvmRpcClient(
            "http://rpc",
            transport=self._rpc_transport(receipt_hash="0x" + "2" * 64),
        )
        with self.assertRaisesRegex(ValueError, "receipt transaction hash"):
            EVMChainVerifier(expected_sender=self.sender, min_confirmations=12).verify_receipt(
                self.evm_auth,
                rpc,
                transaction_hash=self.tx_hash,
            )

    def test_erc20_success_requires_exact_transfer_event(self):
        recipient_word = self.destination[2:].rjust(64, "0")
        amount = 42_000_000
        amount_word = format(amount, "064x")
        transfer_input = "0xa9059cbb" + recipient_word + amount_word
        transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        sender_topic = "0x" + self.sender[2:].rjust(64, "0")
        matching_log = {
            "address": self.token,
            "topics": [
                transfer_topic,
                sender_topic,
                "0x" + recipient_word,
            ],
            "data": "0x" + amount_word,
        }
        auth = {
            "payload": {
                **self.evm_auth["payload"],
                "action": {
                    "action_type": "payment",
                    "metadata": {
                        "evm_transaction": {
                            "chain_id": 5050,
                            "to": self.token,
                            "value_wei": 0,
                            "data": transfer_input,
                        }
                    },
                },
            }
        }
        rpc = EvmRpcClient(
            "http://rpc",
            transport=self._rpc_transport(tx_input=transfer_input, logs=[matching_log]),
        )
        observed = EVMChainVerifier(expected_sender=self.sender, min_confirmations=12).verify_receipt(
            auth,
            rpc,
            transaction_hash=self.tx_hash,
        )
        self.assertEqual(observed.effect_status, "SUCCEEDED")

        rpc_without_log = EvmRpcClient(
            "http://rpc",
            transport=self._rpc_transport(tx_input=transfer_input, logs=[]),
        )
        with self.assertRaisesRegex(ValueError, "no matching Transfer event"):
            EVMChainVerifier(expected_sender=self.sender, min_confirmations=12).verify_receipt(
                auth,
                rpc_without_log,
                transaction_hash=self.tx_hash,
            )

    def test_solana_confirmed_is_independent_observation(self):
        def transport(endpoint, payload, headers, timeout):
            req = json.loads(payload)
            if req["method"] == "getSignatureStatuses":
                return json.dumps({"result": {"value": [{
                    "err": None,
                    "slot": 42,
                    "confirmations": 1,
                    "confirmationStatus": "finalized",
                }]}}).encode()
            raise AssertionError(req["method"])

        observed = SolanaChainVerifier().verify_signature(
            self.sol_auth,
            SolanaRpcClient("http://sol", transport=transport),
            signature="sig-1",
            observed_at=20.0,
        )
        self.assertEqual(observed.effect_status, "SUCCEEDED")
        self.assertEqual(observed.observation["slot"], 42)

    def test_solana_failed_is_failed(self):
        def transport(endpoint, payload, headers, timeout):
            return json.dumps({"result": {"value": [{
                "err": {"custom": 1},
                "slot": 43,
                "confirmationStatus": "confirmed",
            }]}}).encode()

        observed = SolanaChainVerifier().verify_signature(
            self.sol_auth,
            SolanaRpcClient("http://sol", transport=transport),
            signature="sig-2",
        )
        self.assertEqual(observed.effect_status, "FAILED")


if __name__ == "__main__":
    unittest.main()
