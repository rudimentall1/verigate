import tempfile
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.storage import Storage
from integrations.agent_sdk import build_agent_enrollment_package
from scripts.enroll_agent import build_enrollment, enroll


class AgentEnrollmentTest(unittest.TestCase):
    def _package(self):
        key = Ed25519PrivateKey.generate()
        now = time.time()
        return build_agent_enrollment_package(
            key,
            agent_id="external-agent",
            capability_id="external-agent-ticket-v1",
            allowed_actions=["payment"],
            allowed_targets=["merchant-001"],
            allowed_resources=["invoice:demo"],
            allowed_purposes=["settle invoice"],
            context_constraints={"environment": "sandbox"},
            issued_at=now - 1,
            expires_at=now + 3600,
        )

    def test_generic_package_contains_public_material_and_exact_capability_scope(self):
        package = self._package()
        self.assertEqual(package["schema_version"], 1)
        self.assertNotIn("private_key", package)
        identity, capability = build_enrollment(package)
        self.assertEqual(identity.agent_id, "external-agent")
        self.assertEqual(capability.capability_id, "external-agent-ticket-v1")
        self.assertEqual(capability.allowed_actions, ("payment",))
        self.assertEqual(capability.allowed_targets, ("merchant-001",))
        self.assertEqual(capability.context_constraints, {"environment": "sandbox"})

    def test_operator_enrollment_is_idempotent_for_exact_package(self):
        package = self._package()
        with tempfile.TemporaryDirectory() as tmp:
            storage = Storage(Path(tmp) / "verigate.db")
            try:
                first = enroll(storage, package)
                second = enroll(storage, package)
                self.assertEqual(first, second)
                self.assertIsNotNone(storage.identity(first[0]))
                self.assertIsNotNone(storage.capability(first[1]))
            finally:
                storage.close()

    def test_package_rejects_empty_scope_and_duplicate_targets(self):
        key = Ed25519PrivateKey.generate()
        common = {
            "agent_id": "external-agent",
            "capability_id": "cap-1",
            "allowed_actions": ["payment"],
            "allowed_targets": ["merchant"],
            "issued_at": time.time() - 1,
            "expires_at": time.time() + 3600,
        }
        with self.assertRaisesRegex(ValueError, "allowed_actions"):
            build_agent_enrollment_package(key, **{**common, "allowed_actions": []})
        with self.assertRaisesRegex(ValueError, "allowed_targets"):
            build_agent_enrollment_package(key, **{**common, "allowed_targets": ["merchant", "merchant"]})

    def test_enrollment_rejects_expired_or_extra_field_package(self):
        package = self._package()
        with self.assertRaisesRegex(ValueError, "expired"):
            build_enrollment(package, now=package["expires_at"] + 1)
        with self.assertRaisesRegex(ValueError, "exactly"):
            build_enrollment({**package, "unexpected": True})


if __name__ == "__main__":
    unittest.main()
