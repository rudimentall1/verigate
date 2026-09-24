import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.receipt import verify_execution_authorization
from core.capabilities import CapabilityRegistry
from core.models import ActionIntent, Capability, Decision, GuardrailDecision
from core.storage import Storage
from core.authority_state import DynamicAuthorityService
from core.policy import Policy


class CapabilityRegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.tmp.name) / "authority.db")
        self.registry = CapabilityRegistry(self.storage)
        self.action = ActionIntent(
            agent_id="agent-trader",
            action_type="rwa.purchase",
            target="GOLD",
            resource="rwa:gold",
            asset="USDC",
            network="base",
            amount=100.0,
        )
        self.capability = Capability(
            capability_id="cap-gold-001",
            agent_id=self.action.agent_id,
            allowed_actions=("rwa.purchase",),
            allowed_targets=("GOLD",),
            allowed_resources=("rwa:gold",),
            allowed_networks=("base",),
            allowed_assets=("USDC",),
            max_per_action={"USDC": 500.0},
        )

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()
    def test_register_and_resolve_active_capability(self):
        self.registry.register(self.capability)
        resolved = self.registry.resolve(self.capability.capability_id)
        self.assertEqual(resolved.digest, self.capability.digest)
        self.assertTrue(self.registry.active(self.capability.capability_id))

    def test_revocation_blocks_future_authority(self):
        self.registry.register(self.capability)
        self.assertTrue(self.registry.revoke(self.capability.capability_id))
        self.assertFalse(self.registry.active(self.capability.capability_id))
        with self.assertRaisesRegex(PermissionError, "not active"):
            self.registry.resolve(self.capability.capability_id)

    def test_scope_is_checked_by_registry(self):
        self.registry.register(self.capability)
        tampered = ActionIntent(
            agent_id=self.action.agent_id,
            action_type="cloud.operation",
            target="GOLD",
        )
        with self.assertRaisesRegex(PermissionError, "action type outside"):
            self.registry.authorize(self.capability.capability_id, tampered)
    def test_revocation_does_not_mutate_an_already_issued_authorization(self):
        action = replace(self.action, amount=10.0)
        self.registry.register(self.capability)
        permitted = self.registry.authorize(self.capability.capability_id, action)
        self.assertEqual(permitted.digest, self.capability.digest)

        private_path = Path(self.tmp.name) / "issuer.key"
        public_path = Path(self.tmp.name) / "issuer.pub"
        generate_keypair(private_path, public_path)

        decision = GuardrailDecision(
            action.intent_id,
            action.agent_id,
            Decision.ALLOW,
            (),
        )
        policy = Policy()
        authority = DynamicAuthorityService(self.storage).snapshot(
            action.agent_id,
            permitted.capability_id,
        )
        from core.authorization import AuthorizationService
        artifacts = AuthorizationService().issue(
            action,
            decision,
            "e" * 64,
            load_private_key(private_path),
            capability=permitted,
            authority=authority,
            policy=policy,
        )
        execution = artifacts["execution_authorization"]

        self.assertTrue(self.registry.revoke(self.capability.capability_id))
        ok, reason = verify_execution_authorization(
            execution, load_public_key(public_path)
        )
        self.assertTrue(ok, reason)


if __name__ == "__main__":
    unittest.main()
