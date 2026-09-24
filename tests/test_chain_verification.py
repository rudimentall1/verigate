import unittest
import json

from enforcement.chain_verification import EVMChainVerifier, SolanaChainVerifier
from enforcement.evm_rpc import EvmRpcClient
from enforcement.solana_rpc import SolanaRpcClient


class ChainVerificationTest(unittest.TestCase):
    def setUp(self):
        self.evm_auth = {"payload": {"authorization_id": "auth-evm", "action_sha256": "a" * 64, "action": {"action_type": "evm.transaction"}}}
        self.sol_auth = {"payload": {"authorization_id": "auth-sol", "action_sha256": "b" * 64, "action": {"action_type": "solana.transaction"}}}

    def test_evm_receipt_is_independent_observation(self):
        def transport(endpoint, payload, headers, timeout):
            req = json.loads(payload)
            if req["method"] == "eth_chainId": return json.dumps({"result": "0x13ba"}).encode()
            return json.dumps({"result": {"status": "0x1", "blockNumber": "0x10", "blockHash": "0xabc", "transactionHash": req["params"][0]}}).encode()
        observed = EVMChainVerifier().verify_receipt(self.evm_auth, EvmRpcClient("http://rpc", transport=transport), transaction_hash="0x" + "1" * 64, observed_at=10.0)
        self.assertEqual(observed.effect_status, "SUCCEEDED")
        self.assertEqual(observed.evidence_kind, "CHAIN_RECEIPT")
        self.assertEqual(observed.observation["chain_id"], 5050)
        self.assertEqual(observed.observation["transaction_hash"], "0x" + "1" * 64)

    def test_evm_pending_is_unknown(self):
        def transport(endpoint, payload, headers, timeout):
            return json.dumps({"result": None if json.loads(payload)["method"] != "eth_chainId" else "0x1"}).encode()
        observed = EVMChainVerifier().verify_receipt(self.evm_auth, EvmRpcClient("http://rpc", transport=transport), transaction_hash="0x1")
        self.assertEqual(observed.effect_status, "UNKNOWN")

    def test_solana_confirmed_is_independent_observation(self):
        def transport(endpoint, payload, headers, timeout):
            req = json.loads(payload)
            if req["method"] == "getSignatureStatuses":
                return json.dumps({"result": {"value": [{"err": None, "slot": 42, "confirmations": 1, "confirmationStatus": "finalized"}]}}).encode()
            raise AssertionError(req["method"])
        observed = SolanaChainVerifier().verify_signature(self.sol_auth, SolanaRpcClient("http://sol", transport=transport), signature="sig-1", observed_at=20.0)
        self.assertEqual(observed.effect_status, "SUCCEEDED")
        self.assertEqual(observed.observation["slot"], 42)

    def test_solana_failed_is_failed(self):
        def transport(endpoint, payload, headers, timeout):
            return json.dumps({"result": {"value": [{"err": {"custom": 1}, "slot": 43, "confirmationStatus": "confirmed"}]}}).encode()
        observed = SolanaChainVerifier().verify_signature(self.sol_auth, SolanaRpcClient("http://sol", transport=transport), signature="sig-2")
        self.assertEqual(observed.effect_status, "FAILED")


if __name__ == "__main__":
    unittest.main()
