import base64
import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.models import ActionIntent
from core.authorization import AuthorizationService
from core.models import GuardrailDecision, Decision
from enforcement.solana import SolanaExecutionAdapter
from core.storage import Storage


class SolanaExecutionAdapterTest(unittest.TestCase):
    def test_exact_serialized_transaction_is_broadcast_once(self):
        with tempfile.TemporaryDirectory() as td:
            private = Path(td) / "issuer.key"
            public = Path(td) / "issuer.pub"
            generate_keypair(private, public)
            storage = Storage(Path(td) / "audit.db")
            try:
                raw = base64.b64encode(b"solana-wire-transaction").decode("ascii")
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
                artifacts = AuthorizationService().issue(
                    intent,
                    decision,
                    "test-policy",
                    load_private_key(private),
                    nonce=intent.intent_id,
                )
                adapter = SolanaExecutionAdapter(storage, load_public_key(public))
                sent = []
                result = adapter.execute(artifacts["execution_authorization"], lambda tx: sent.append(tx) or "sig")
                self.assertEqual(result, "sig")
                self.assertEqual(sent, [{"encoding": "base64", "serialized_transaction": raw}])
                with self.assertRaises(PermissionError):
                    adapter.execute(artifacts["execution_authorization"], lambda tx: sent.append(tx))
                self.assertEqual(len(sent), 1)
            finally:
                storage.close()

    def test_invalid_serialized_transaction_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            private = Path(td) / "issuer.key"
            public = Path(td) / "issuer.pub"
            generate_keypair(private, public)
            storage = Storage(Path(td) / "audit.db")
            try:
                intent = ActionIntent(
                    agent_id="solana-agent",
                    action_type="token.transfer",
                    target="recipient",
                    asset="USDC",
                    network="solana",
                    metadata={"solana_transaction": "not-base64"},
                )
                decision = GuardrailDecision(
                    intent_id=intent.intent_id,
                    agent_id=intent.agent_id,
                    decision=Decision.ALLOW,
                    matched_rules=(),
                )
                artifacts = AuthorizationService().issue(
                    intent, decision, "test-policy", load_private_key(private), nonce=intent.intent_id
                )
                adapter = SolanaExecutionAdapter(storage, load_public_key(public))
                ok, reason = adapter.consume(artifacts["execution_authorization"])
                self.assertFalse(ok)
                self.assertEqual(reason, "invalid Solana transaction encoding")
            finally:
                storage.close()


if __name__ == "__main__":
    unittest.main()
