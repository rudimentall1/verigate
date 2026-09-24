import base64
import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.models import ActionIntent, Capability
from core.authorization import AuthorizationService
from core.models import GuardrailDecision, Decision
from core.authority_state import DynamicAuthorityService
from core.policy import Policy
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
                capability = Capability(
                    capability_id="cap-solana-exec",
                    agent_id=intent.agent_id,
                    allowed_actions=("token.transfer",),
                    allowed_targets=("recipient",),
                    allowed_networks=("solana",),
                    allowed_assets=("USDC",),
                )
                storage.register_capability(capability)
                authority = DynamicAuthorityService(storage).snapshot(
                    intent.agent_id, capability.capability_id
                )
                artifacts = AuthorizationService().issue(
                    intent,
                    decision,
                    Policy().digest,
                    load_private_key(private),
                    nonce=intent.intent_id,
                    capability=capability,
                    authority=authority,
                    policy=Policy(),
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
                capability = Capability(
                    capability_id="cap-solana-invalid",
                    agent_id=intent.agent_id,
                    allowed_actions=("token.transfer",),
                    allowed_targets=("recipient",),
                    allowed_networks=("solana",),
                    allowed_assets=("USDC",),
                )
                storage.register_capability(capability)
                authority = DynamicAuthorityService(storage).snapshot(
                    intent.agent_id, capability.capability_id
                )
                artifacts = AuthorizationService().issue(
                    intent,
                    decision,
                    Policy().digest,
                    load_private_key(private),
                    nonce=intent.intent_id,
                    capability=capability,
                    authority=authority,
                    policy=Policy(),
                )
                adapter = SolanaExecutionAdapter(storage, load_public_key(public))
                ok, reason = adapter.consume(artifacts["execution_authorization"])
                self.assertFalse(ok)
                self.assertEqual(reason, "invalid Solana transaction encoding")
            finally:
                storage.close()


if __name__ == "__main__":
    unittest.main()
