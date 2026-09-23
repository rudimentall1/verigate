import base64
import hashlib
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.receipt import verify_execution_authorization
from core.engine import GuardrailEngine
from core.identity import IdentityRegistry, sign_action_intent, verify_action_signature
from core.models import ActionIntent, AgentIdentity, Capability
from core.policy import Policy
from core.storage import Storage


def make_identity(agent_id: str, private_key: Ed25519PrivateKey):
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    key_id = hashlib.sha256(raw).hexdigest()
    identity = AgentIdentity(
        agent_id=agent_id,
        public_key_b64=base64.b64encode(raw).decode("ascii"),
        key_id=key_id,
    )
    return identity, key_id
class IdentityRegistryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.tmp.name) / "identity.db")
        self.registry = IdentityRegistry(self.storage)
        self.agent_private = Ed25519PrivateKey.generate()
        self.identity, self.identity_id = make_identity(
            "agent-identity", self.agent_private
        )
        self.action = ActionIntent(
            agent_id="agent-identity",
            action_type="payment",
            target="merchant",
            resource="invoice:123",
            amount=1.0,
            asset="USDC",
            network="base",
        )

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def test_register_resolve_and_fingerprint(self):
        self.registry.register(self.identity)
        resolved = self.registry.resolve(self.identity_id)
        self.assertEqual(resolved.digest, self.identity.digest)
        self.assertTrue(self.registry.active(self.identity_id))

    def test_action_signature_is_verified_against_registered_key(self):
        self.registry.register(self.identity)
        signature = sign_action_intent(
            self.action, self.identity_id, self.agent_private
        )
        valid, reason = verify_action_signature(
            self.action, self.identity_id, signature, self.identity
        )
        self.assertTrue(valid, reason)
    def test_tampered_action_and_revoked_identity_fail_closed(self):
        self.registry.register(self.identity)
        signature = sign_action_intent(
            self.action, self.identity_id, self.agent_private
        )
        tampered = ActionIntent(
            agent_id=self.action.agent_id,
            action_type=self.action.action_type,
            target="attacker",
            resource=self.action.resource,
            amount=self.action.amount,
            asset=self.action.asset,
            network=self.action.network,
        )
        valid, _ = verify_action_signature(
            tampered, self.identity_id, signature, self.identity
        )
        self.assertFalse(valid)
        self.assertTrue(self.registry.revoke(self.identity_id))
        with self.assertRaises(PermissionError):
            self.registry.authorize_action(
                self.identity_id, self.action, signature
            )

    def test_wrong_key_fingerprint_is_rejected(self):
        wrong = AgentIdentity(
            agent_id="agent-identity",
            public_key_b64=self.identity.public_key_b64,
            key_id="00" * 32,
        )
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            self.registry.register(wrong)
    def test_engine_binds_identity_and_capability_to_authorization(self):
        self.registry.register(self.identity)
        capability = Capability(
            capability_id="cap-identity-001",
            agent_id="agent-identity",
            identity_id=self.identity_id,
            allowed_actions=("payment",),
            allowed_targets=("merchant",),
            allowed_networks=("base",),
            allowed_assets=("USDC",),
        )
        self.storage.register_capability(capability)

        issuer_private_path = Path(self.tmp.name) / "issuer.key"
        issuer_public_path = Path(self.tmp.name) / "issuer.pub"
        generate_keypair(issuer_private_path, issuer_public_path)

        engine = GuardrailEngine(
            Policy(
                allowed_networks=["base"],
                allowed_assets=["USDC"],
                raw={"allowed_networks": ["base"], "allowed_assets": ["USDC"]},
            ),
            self.storage,
        )
        signature = sign_action_intent(
            self.action, self.identity_id, self.agent_private
        )
        artifacts = engine.authorize_with_identity(
            self._payment(),
            capability.capability_id,
            self.identity_id,
            signature,
            load_private_key(issuer_private_path),
        )
        execution = artifacts["execution_authorization"]
        self.assertEqual(execution["payload"]["identity_id"], self.identity_id)
        self.assertEqual(execution["payload"]["identity_sha256"], self.identity.digest)
        self.assertEqual(execution["payload"]["capability_id"], capability.capability_id)
        self.assertEqual(
            execution["payload"]["capability_sha256"], capability.digest
        )
        self.assertTrue(
            verify_execution_authorization(
                execution, load_public_key(issuer_public_path)
            )[0]
        )

    def _payment(self):
        return __import__("core.models", fromlist=["PaymentIntent"]).PaymentIntent(
            agent_id="agent-identity",
            payee="merchant",
            asset="USDC",
            network="base",
            amount=1.0,
            resource="invoice:123",
            intent_id=self.action.intent_id,
            timestamp=self.action.timestamp,
        )


if __name__ == "__main__":
    unittest.main()
