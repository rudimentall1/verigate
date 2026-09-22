import base64
import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authorization import AuthorizationService
from core.models import ActionIntent, Decision, GuardrailDecision
from core.storage import Storage
from enforcement.solana import SolanaExecutionAdapter
from enforcement.solana_rpc import SolanaRpcClient, SolanaRpcError


class SolanaRpcClientTest(unittest.TestCase):
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
                raw = base64.b64encode(b"signed-solana-transaction").decode("ascii")
                intent = ActionIntent(
                    agent_id="solana-agent",
                    action_type="token.transfer",
                    target="recipient",
                    asset="USDC",
                    network="solana",
                    metadata={"solana_transaction": raw},
                )
                decision = GuardrailDecision(
                    intent_id=intent.intent_id,
                    agent_id=intent.agent_id,
                    decision=Decision.ALLOW,
                    matched_rules=(),
                )
                auth = AuthorizationService().issue(
                    intent, decision, "policy", load_private_key(private), nonce=intent.intent_id
                )["execution_authorization"]

                rpc = SolanaRpcClient(
                    "https://example.invalid",
                    transport=lambda *_: b'{"jsonrpc":"2.0","id":1,"result":"5nSig"}',
                )
                adapter = SolanaExecutionAdapter(storage, load_public_key(public))
                self.assertEqual(adapter.execute(auth, rpc.send_transaction), "5nSig")
            finally:
                storage.close()


if __name__ == "__main__":
    unittest.main()
