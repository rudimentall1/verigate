import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authorization import AuthorizationService
from core.models import ActionIntent, Capability, Decision, GuardrailDecision
from core.storage import Storage
from core.authority_state import DynamicAuthorityService
from core.policy import Policy
from enforcement.evm import EVMExecutionAdapter
from enforcement.evm_rpc import EvmRpcClient, EvmRpcError


class EvmRpcClientTest(unittest.TestCase):
    def test_chain_id_parsing(self):
        calls = []

        def transport(endpoint, payload, headers, timeout):
            calls.append(payload)
            return b'{"jsonrpc":"2.0","id":1,"result":"0x2105"}'

        client = EvmRpcClient("https://example.invalid", transport=transport)
        self.assertEqual(client.chain_id(), 8453)
        self.assertIn(b'"eth_chainId"', calls[0])

    def test_send_raw_transaction_uses_exact_wire_payload(self):
        calls = []

        def transport(endpoint, payload, headers, timeout):
            calls.append(payload)
            return b'{"jsonrpc":"2.0","id":1,"result":"0xabc123"}'

        client = EvmRpcClient("https://example.invalid", transport=transport)
        self.assertEqual(client.send_raw_transaction("0xdeadbeef"), "0xabc123")
        self.assertIn(b'"eth_sendRawTransaction"', calls[0])
        self.assertIn(b'"0xdeadbeef"', calls[0])

    def test_invalid_wire_payload_fails_closed(self):
        client = EvmRpcClient("https://example.invalid", transport=lambda *_: b"{}")
        with self.assertRaises(ValueError):
            client.send_raw_transaction("0x123")

    def test_rpc_error_is_raised(self):
        client = EvmRpcClient(
            "https://example.invalid",
            transport=lambda *_: b'{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"rejected"}}',
        )
        with self.assertRaises(EvmRpcError):
            client.send_raw_transaction("0xdeadbeef")


class EvmRpcExecutionIntegrationTest(unittest.TestCase):
    def test_signed_wire_transaction_is_bound_to_authorization(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            private = root / "issuer.key"
            public = root / "issuer.pub"
            generate_keypair(private, public)
            storage = Storage(root / "audit.db")
            try:
                intent = ActionIntent(
                    agent_id="evm-agent",
                    action_type="token.transfer",
                    target="merchant",
                    asset="USDC",
                    network="base",
                    metadata={
                        "evm_transaction": {
                            "chain_id": 8453,
                            "to": "0xMerchant",
                            "value_wei": 0,
                            "data": "0x",
                            "signed_raw_transaction": "0xdeadbeef",
                        }
                    },
                )
                decision = GuardrailDecision(
                    intent_id=intent.intent_id,
                    agent_id=intent.agent_id,
                    decision=Decision.ALLOW,
                    matched_rules=(),
                )
                capability = Capability(
                    capability_id="cap-evm-rpc",
                    agent_id=intent.agent_id,
                    allowed_actions=("token.transfer",),
                    allowed_targets=("merchant",),
                    allowed_networks=("base",),
                    allowed_assets=("USDC",),
                )
                storage.register_capability(capability)
                authority = DynamicAuthorityService(storage).snapshot(
                    intent.agent_id, capability.capability_id
                )
                auth = AuthorizationService().issue(
                    intent,
                    decision,
                    "policy",
                    load_private_key(private),
                    nonce=intent.intent_id,
                    capability=capability,
                    authority=authority,
                    policy=Policy(),
                )["execution_authorization"]
                adapter = EVMExecutionAdapter(storage, load_public_key(public))
                rpc = EvmRpcClient(
                    "https://example.invalid",
                    transport=lambda *_: b'{"jsonrpc":"2.0","id":1,"result":"0xabc123"}',
                )
                tx = adapter._transaction(auth["payload"]["action"])
                self.assertEqual(rpc.send_raw_transaction(tx["signed_raw_transaction"]), "0xabc123")
                self.assertTrue(tx["signed_raw_transaction"] in auth["payload"]["action"]["metadata"]["evm_transaction"]["signed_raw_transaction"])
            finally:
                storage.close()


if __name__ == "__main__":
    unittest.main()
