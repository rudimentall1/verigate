import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.receipt import verify_execution_authorization, verify_receipt
from core.authorization import AuthorizationService
from core.models import ActionIntent, Capability, Decision, GuardrailDecision


class AuthorizationServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.priv = Path(self.tmpdir.name) / "issuer.key"
        self.pub = Path(self.tmpdir.name) / "issuer.pub"
        generate_keypair(self.priv, self.pub)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _action(self):
        return ActionIntent(
            agent_id="agent-rwa",
            action_type="evm.transaction",
            target="0xasset",
            resource="chain:8453",
            metadata={"evm_transaction": {"chain_id": 8453, "to": "0xasset", "value_wei": 0, "data": "0x"}},
        )

    def test_generic_action_can_mint_portable_capability(self):
        action = self._action()
        decision = GuardrailDecision(action.intent_id, action.agent_id, Decision.ALLOW, ())
        artifacts = AuthorizationService().issue(
            action, decision, "a" * 64, load_private_key(self.priv)
        )
        receipt = artifacts["decision_receipt"]
        execution = artifacts["execution_authorization"]
        self.assertTrue(verify_receipt(receipt, load_public_key(self.pub))[0])
        self.assertTrue(verify_execution_authorization(execution, load_public_key(self.pub))[0])
        self.assertEqual(execution["payload"]["action"], action.as_dict())

    def test_warn_never_mints_execution_capability(self):
        action = self._action()
        decision = GuardrailDecision(action.intent_id, action.agent_id, Decision.WARN, ())
        artifacts = AuthorizationService().issue(
            action, decision, "b" * 64, load_private_key(self.priv)
        )
        self.assertIsNone(artifacts["execution_authorization"])

    def test_capability_scope_is_bound_to_execution_authorization(self):
        action = self._action()
        capability = Capability(
            capability_id="cap-rwa-001",
            agent_id=action.agent_id,
            allowed_actions=("evm.transaction",),
            allowed_targets=(action.target,),
        )
        decision = GuardrailDecision(action.intent_id, action.agent_id, Decision.ALLOW, ())
        artifacts = AuthorizationService().issue(
            action, decision, "c" * 64, load_private_key(self.priv), capability=capability
        )
        execution = artifacts["execution_authorization"]
        self.assertEqual(execution["payload"]["capability_id"], capability.capability_id)
        self.assertEqual(execution["payload"]["capability_version"], capability.version)
        self.assertTrue(verify_execution_authorization(execution, load_public_key(self.pub))[0])

    def test_capability_mismatch_cannot_mint_execution_authorization(self):
        action = self._action()
        capability = Capability(
            capability_id="cap-wrong-agent",
            agent_id="another-agent",
            allowed_actions=("evm.transaction",),
        )
        decision = GuardrailDecision(action.intent_id, action.agent_id, Decision.ALLOW, ())
        with self.assertRaises(PermissionError):
            AuthorizationService().issue(
                action, decision, "d" * 64, load_private_key(self.priv), capability=capability
            )


if __name__ == "__main__":
    unittest.main()
