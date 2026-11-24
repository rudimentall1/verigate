import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authorization import AuthorizationService
from core.models import ActionIntent, Capability, Decision, GuardrailDecision
from core.storage import Storage
from core.authority_state import DynamicAuthorityService
from core.policy import Policy
from enforcement.solana import SolanaExecutionAdapter
from enforcement.solana_rpc import SolanaRpcClient, SolanaRpcError
from solana_fixtures import make_signed_transfer


class SolanaRpcClientTest(unittest.TestCase):
    def test_get_genesis_hash_parses_cluster_identity(self):
        calls = []

        def transport(endpoint, payload, headers, timeout):
            calls.append(payload)
            return b'{"jsonrpc":"2.0","id":1,"result":"EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG"}'

        client = SolanaRpcClient("https://example.invalid", transport=transport)
        self.assertEqual(
            client.get_genesis_hash(),
            "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG",
        )
        self.assertEqual(len(calls), 1)
        self.assertIn(b'"method":"getGenesisHash"', calls[0])
        self.assertIn(b'"params":[]', calls[0])

    def test_get_genesis_hash_rejects_missing_result(self):
        client = SolanaRpcClient(
            "https://example.invalid",
            transport=lambda *_: b'{"jsonrpc":"2.0","id":1,"result":null}',
        )
        with self.assertRaises(SolanaRpcError):
            client.get_genesis_hash()

    def test_get_genesis_hash_propagates_rpc_error(self):
        client = SolanaRpcClient(
            "https://example.invalid",
            transport=lambda *_: b'{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"bad"}}',
        )
        with self.assertRaises(SolanaRpcError):
            client.get_genesis_hash()

    def test_get_balance_parses_lamports(self):
        client = SolanaRpcClient(
            "https://example.invalid",
            transport=lambda *_: b'{"jsonrpc":"2.0","id":1,"result":{"context":{"slot":1},"value":1234567}}',
        )
        self.assertEqual(client.get_balance("Sender"), 1234567)

    def test_send_transaction_uses_fail_closed_rpc_options(self):
        calls = []

        def transport(endpoint, payload, headers, timeout):
            calls.append((endpoint, payload, headers, timeout))
            return b'{"jsonrpc":"2.0","id":1,"result":"5nSig"}'

        client = SolanaRpcClient("https://example.invalid", transport=transport)
        signature = client.send_transaction("U0lHTkFUVVJF")
        self.assertEqual(signature, "5nSig")
        self.assertEqual(len(calls), 1)
        self.assertIn(b'"skipPreflight":false', calls[0][1])
        self.assertIn(b'"maxRetries":0', calls[0][1])

    def test_rpc_error_is_raised(self):
        client = SolanaRpcClient(
            "https://example.invalid",
            transport=lambda *_: b'{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"bad"}}',
        )
        with self.assertRaises(SolanaRpcError):
            client.send_transaction("U0lHTkFUVVJF")


class SolanaExecutionIntegrationTest(unittest.TestCase):
    def test_authorized_transaction_can_use_rpc_broadcaster(self):
        with tempfile.TemporaryDirectory() as td:
            private = Path(td) / "issuer.key"
            public = Path(td) / "issuer.pub"
            generate_keypair(private, public)
            storage = Storage(Path(td) / "audit.db")
            try:
                raw, sender_address, recipient_address = make_signed_transfer()
                intent = ActionIntent(
                    agent_id="solana-agent",
                    action_type="native.transfer",
                    target=recipient_address,
                    amount=0.001,
                    asset="SOL",
                    network="solana",
                    metadata={"solana_transaction": raw, "solana_sender": sender_address, "destination": recipient_address, "solana_genesis_hash": "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG"},
                )
                decision = GuardrailDecision(
                    intent_id=intent.intent_id,
                    agent_id=intent.agent_id,
                    decision=Decision.ALLOW,
                    matched_rules=(),
                )
                capability = Capability(
                    capability_id="cap-solana-rpc",
                    agent_id=intent.agent_id,
                    allowed_actions=("native.transfer",),
                    allowed_targets=(recipient_address,),
                    allowed_networks=("solana",),
                    allowed_assets=("SOL",),
                )
                storage.register_capability(capability)
                authority = DynamicAuthorityService(storage).snapshot(
                    intent.agent_id, capability.capability_id
                )
                auth = AuthorizationService().issue(
                    intent,
                    decision,
                    Policy().digest,
                    load_private_key(private),
                    nonce=intent.intent_id,
                    capability=capability,
                    authority=authority,
                    policy=Policy(),
                )["execution_authorization"]

                rpc = SolanaRpcClient(
                    "https://example.invalid",
                    transport=lambda *_: b'{"jsonrpc":"2.0","id":1,"result":"5nSig"}',
                )
                adapter = SolanaExecutionAdapter(storage, load_public_key(public), lambda: "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG")
                self.assertEqual(adapter.execute(auth, rpc.send_transaction), "5nSig")
            finally:
                storage.close()


if __name__ == "__main__":
    unittest.main()
