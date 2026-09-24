import json
import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.external_state import external_state_digest_from_observation
from enforcement.evm_rpc import EvmRpcClient
from enforcement.external_state import EVMExternalStateVerifier


class FakeTransport:
    def __init__(self, code="0x6000", storage="0x" + "00" * 32, chain="0x1"):
        self.code = code
        self.storage = storage
        self.chain = chain

    def __call__(self, endpoint, payload, headers, timeout):
        request = json.loads(payload)
        method = request["method"]
        if method == "eth_chainId": result = self.chain
        elif method == "eth_getCode": result = self.code
        elif method == "eth_getStorageAt": result = self.storage
        else: raise AssertionError(method)
        return json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}).encode()


class EVMExternalStateTest(unittest.TestCase):
    def _binding(self, transport):
        rpc = EvmRpcClient("mock://rpc", transport=transport)
        observation = {
            "kind": "evm.state", "chain_id": 1, "address": "0x" + "11" * 20,
            "block_tag": "latest", "code": transport.code.lower(),
            "storage": {("0x" + "00" * 32): transport.storage.lower()},
        }
        return rpc, {
            "kind": "evm.state", "reference": "1:0x" + "11" * 20,
            "digest": external_state_digest_from_observation(observation),
            "chain_id": 1, "address": "0x" + "11" * 20,
            "block_tag": "latest", "storage_slots": ["0x" + "00" * 32],
        }

    def test_matching_live_state(self):
        transport = FakeTransport()
        rpc, binding = self._binding(transport)
        ok, reason = EVMExternalStateVerifier(rpc)(binding, {})
        self.assertTrue(ok, reason)

    def test_storage_drift_blocks(self):
        transport = FakeTransport()
        rpc, binding = self._binding(transport)
        transport.storage = "0x" + "01" * 32
        ok, reason = EVMExternalStateVerifier(rpc)(binding, {})
        self.assertFalse(ok)
        self.assertIn("digest changed", reason)

    def test_chain_drift_blocks(self):
        transport = FakeTransport()
        rpc, binding = self._binding(transport)
        transport.chain = "0x2"
        ok, reason = EVMExternalStateVerifier(rpc)(binding, {})
        self.assertFalse(ok)
        self.assertIn("chain id changed", reason)


if __name__ == "__main__": unittest.main()
