import base64
import tempfile
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.models import ActionIntent
from core.storage import Storage
from scripts.enroll_agent_arc import build_enrollment, enroll, revoke


class ArcAgentEnrollmentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.temp.name) / "enrollment.db")
        self.now = time.time()
        self.key = Ed25519PrivateKey.generate()
        raw = self.key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.package = {
            "schema_version": 1,
            "agent_id": "independent-agent-01",
            "public_key_b64": base64.b64encode(raw).decode("ascii"),
            "capability_id": "cap-independent-agent-arc-v1",
            "allowed_targets": ["0x2222222222222222222222222222222222222222"],
            "max_per_action_usdc": 12.5,
            "issued_at": self.now - 1,
            "expires_at": self.now + 3600,
        }

    def tearDown(self):
        self.storage.close()
        self.temp.cleanup()

    def test_valid_package_registers_identity_and_arc_capability(self):
        identity_id, capability_id = enroll(self.storage, self.package, now=self.now)
        identity = self.storage.identity(identity_id)
        capability = self.storage.capability(capability_id)
        self.assertEqual(identity.agent_id, self.package["agent_id"])
        self.assertEqual(capability.identity_id, identity_id)
        self.assertEqual(capability.allowed_networks, ("arc",))
        self.assertEqual(capability.allowed_assets, ("USDC",))
        self.assertEqual(capability.allowed_actions, ("payment",))
        self.assertTrue(self.storage.identity_is_active(identity_id))
        self.assertTrue(self.storage.capability_is_active(capability_id))

    def test_rejects_malformed_key_and_unknown_private_key_field(self):
        malformed = dict(self.package, public_key_b64="not-base64!")
        with self.assertRaisesRegex(ValueError, "public_key_b64"):
            build_enrollment(malformed, now=self.now)
        with self.assertRaisesRegex(ValueError, "exactly"):
            build_enrollment(dict(self.package, private_key="must-not-be-accepted"), now=self.now)

    def test_rejects_expired_package_and_invalid_target_scope(self):
        with self.assertRaisesRegex(ValueError, "expired"):
            build_enrollment(dict(self.package, expires_at=self.now - 1), now=self.now)
        with self.assertRaisesRegex(ValueError, "Arc EVM addresses"):
            build_enrollment(dict(self.package, allowed_targets=["*"]), now=self.now)

    def test_capability_enforces_target_and_per_action_limit(self):
        identity_id, capability_id = enroll(self.storage, self.package, now=self.now)
        capability = self.storage.capability(capability_id)
        permitted, _ = capability.permits(ActionIntent(
            agent_id=self.package["agent_id"], action_type="payment",
            target=self.package["allowed_targets"][0], amount_exact="12.50",
            asset="USDC", network="arc",
        ), now=self.now)
        self.assertTrue(permitted)
        denied_target, _ = capability.permits(ActionIntent(
            agent_id=self.package["agent_id"], action_type="payment",
            target="0x3333333333333333333333333333333333333333",
            amount_exact="1", asset="USDC", network="arc",
        ), now=self.now)
        denied_amount, _ = capability.permits(ActionIntent(
            agent_id=self.package["agent_id"], action_type="payment",
            target=self.package["allowed_targets"][0], amount_exact="12.5001",
            asset="USDC", network="arc",
        ), now=self.now)
        self.assertFalse(denied_target)
        self.assertFalse(denied_amount)

    def test_exact_replay_is_idempotent_but_conflicts_are_rejected(self):
        first = enroll(self.storage, self.package, now=self.now)
        second = enroll(self.storage, self.package, now=self.now)
        self.assertEqual(first, second)
        conflicting = dict(self.package, max_per_action_usdc=25)
        with self.assertRaisesRegex(ValueError, "different authority"):
            enroll(self.storage, conflicting, now=self.now)

    def test_revocation_disables_capability_and_identity(self):
        identity_id, capability_id = enroll(self.storage, self.package, now=self.now)
        revoke(self.storage, identity_id, capability_id)
        self.assertFalse(self.storage.identity_is_active(identity_id))
        self.assertFalse(self.storage.capability_is_active(capability_id))


if __name__ == "__main__":
    unittest.main()
