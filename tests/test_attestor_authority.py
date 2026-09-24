import base64
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.attestor import AttestorAuthorityService
from core.governance import GovernanceMember, GovernancePolicy, governor_id
from core.storage import Storage


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def approval(action, private_key):
    payload = {
        "governance_version": 1,
        "action_digest": hashlib.sha256(canonical(action)).hexdigest(),
        "governor_id": governor_id(private_key.public_key()),
        "role": "governor",
        "approval_id": "approval-" + action["action_id"],
        "issued_at": time.time(),
        "expires_at": time.time() + 120,
        "nonce": "nonce-" + action["action_id"],
    }
    return {
        "payload": payload,
        "signature": base64.b64encode(private_key.sign(canonical(payload))).decode(),
        "algorithm": "Ed25519",
    }


class AttestorAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(str(Path(self.tmp.name) / "test.db"))
        self.gov_key = Ed25519PrivateKey.generate()
        self.policy = GovernancePolicy(
            policy_id="test-governance",
            version=1,
            threshold=1,
            members=(GovernanceMember.from_public_key(self.gov_key.public_key(), "governor"),),
            allowed_actions=(
                "ATTESTOR_REGISTER",
                "ATTESTOR_ACTIVATE",
                "ATTESTOR_ROTATE",
                "ATTESTOR_REVOKE",
                "ATTESTOR_EXPIRE",
            ),
        )
        self.service = AttestorAuthorityService(self.storage)

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def action(self, action, key=None):
        return self.service.build_action(
            action=action,
            attestor_id="verifier-1",
            reason="governed lifecycle test",
            governance_policy_sha256=self.policy.digest,
            public_key_b64=key,
            attestor_type="EXTERNAL_VERIFIER" if key else None,
        )

    def test_governed_register_rotate_revoke(self):
        key1 = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        a1 = self.action("ATTESTOR_REGISTER", base64.b64encode(key1).decode())
        result = self.service.apply(a1, [approval(a1, self.gov_key)], self.policy)
        self.assertEqual(result["attestor"]["status"], "ACTIVE")
        first_key_id = result["attestor"]["key_id"]

        key2 = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        a2 = self.action("ATTESTOR_ROTATE", base64.b64encode(key2).decode())
        result = self.service.apply(a2, [approval(a2, self.gov_key)], self.policy)
        self.assertEqual(result["attestor"]["status"], "ACTIVE")
        self.assertNotEqual(result["attestor"]["key_id"], first_key_id)

        a3 = self.service.build_action(
            action="ATTESTOR_REVOKE",
            attestor_id="verifier-1",
            reason="revoke test",
            governance_policy_sha256=self.policy.digest,
        )
        result = self.service.apply(a3, [approval(a3, self.gov_key)], self.policy)
        self.assertEqual(result["attestor"]["status"], "REVOKED")
        self.assertEqual(len(self.storage.attestor_governance_actions("verifier-1")), 3)

    def test_wrong_policy_digest_is_rejected(self):
        key = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        action = self.service.build_action(
            action="ATTESTOR_REGISTER",
            attestor_id="verifier-2",
            reason="negative test",
            governance_policy_sha256="0" * 64,
            public_key_b64=base64.b64encode(key).decode(),
            attestor_type="EXTERNAL_VERIFIER",
        )
        with self.assertRaises(PermissionError):
            self.service.apply(action, [approval(action, self.gov_key)], self.policy)


if __name__ == "__main__":
    unittest.main()
