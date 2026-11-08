import base64
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.governance import GovernanceMember, GovernancePolicy, governor_id
from core.storage import Storage
from core.wallet_enrollment import WalletEnrollmentService, installation_principal


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def approval(action, private_key, suffix):
    payload = {
        "governance_version": 1,
        "action_digest": hashlib.sha256(canonical(action)).hexdigest(),
        "governor_id": governor_id(private_key.public_key()),
        "role": "governor",
        "approval_id": f"approval-{suffix}-{action['action_id']}",
        "issued_at": time.time(),
        "expires_at": time.time() + 120,
        "nonce": f"nonce-{suffix}-{action['action_id']}",
    }
    return {
        "payload": payload,
        "signature": base64.b64encode(private_key.sign(canonical(payload))).decode(),
        "algorithm": "Ed25519",
    }


class WalletEnrollmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(str(Path(self.tmp.name) / "wallets.db"))
        self.gov1 = Ed25519PrivateKey.generate()
        self.gov2 = Ed25519PrivateKey.generate()
        self.policy = GovernancePolicy(
            policy_id="wallet-enrollment-test", version=1, threshold=2,
            members=(
                GovernanceMember.from_public_key(self.gov1.public_key(), "governor"),
                GovernanceMember.from_public_key(self.gov2.public_key(), "governor"),
            ),
            allowed_actions=("WALLET_ENROLL", "WALLET_REVOKE"),
        )
        self.service = WalletEnrollmentService(self.storage)
        self.issuer = Ed25519PrivateKey.generate()
        self.issuer_b64 = base64.b64encode(
            self.issuer.public_key().public_bytes_raw()
        ).decode()

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def make_enroll(self, *, issuer=None, wallet="0x" + "a" * 40, chain=8453, confirmations=12):
        pub = issuer or self.issuer_b64
        return self.service.build_action(
            action="WALLET_ENROLL", reason="operator verified wallet ownership",
            governance_policy_sha256=self.policy.digest,
            issuer_public_key_b64=pub, chain_id=chain, network="base",
            wallet_address=wallet, min_confirmations=confirmations,
        )

    def approvals(self, action):
        return [approval(action, self.gov1, "one"), approval(action, self.gov2, "two")]

    def test_governed_enrollment_binds_installation_key_chain_wallet_and_finality(self):
        action = self.make_enroll()
        result = self.service.apply(action, self.approvals(action), self.policy)
        enrollment = result["enrollment"]
        expected_principal, expected_key_id = installation_principal(self.issuer_b64)
        self.assertEqual(enrollment["installation_principal"], expected_principal)
        self.assertEqual(enrollment["issuer_key_id"], expected_key_id)
        self.assertEqual(enrollment["chain_id"], 8453)
        self.assertEqual(enrollment["network"], "base")
        self.assertEqual(enrollment["wallet_address"], "0x" + "a" * 40)
        self.assertEqual(enrollment["min_confirmations"], 12)
        self.assertEqual(enrollment["status"], "ACTIVE")
        self.assertEqual(
            self.storage.wallet_enrollment_for_wallet(expected_principal, 8453, "0x" + "A" * 40)["enrollment_id"],
            enrollment["enrollment_id"],
        )

    def test_verifier_factory_uses_only_active_enrollment_values(self):
        action = self.make_enroll()
        enrollment = self.service.apply(action, self.approvals(action), self.policy)["enrollment"]
        verifier = self.service.evm_verifier_for_wallet(
            enrollment["installation_principal"], enrollment["chain_id"], enrollment["wallet_address"],
        )
        self.assertEqual(verifier.expected_sender, enrollment["wallet_address"])
        self.assertEqual(verifier.min_confirmations, enrollment["min_confirmations"])
        revoke = self.service.build_action(
            action="WALLET_REVOKE", reason="rotate wallet", governance_policy_sha256=self.policy.digest,
            enrollment_id=enrollment["enrollment_id"],
        )
        self.service.apply(revoke, self.approvals(revoke), self.policy)
        with self.assertRaises(PermissionError):
            self.service.evm_verifier_for_wallet(
                enrollment["installation_principal"], enrollment["chain_id"], enrollment["wallet_address"],
            )

    def test_revoke_is_governed_and_preserves_audit_history(self):
        register = self.make_enroll()
        enrolled = self.service.apply(register, self.approvals(register), self.policy)["enrollment"]
        revoke = self.service.build_action(
            action="WALLET_REVOKE", reason="wallet compromised",
            governance_policy_sha256=self.policy.digest,
            enrollment_id=enrolled["enrollment_id"],
        )
        result = self.service.apply(revoke, self.approvals(revoke), self.policy)
        self.assertEqual(result["enrollment"]["status"], "REVOKED")
        self.assertEqual(len(self.storage.wallet_enrollment_governance_actions(enrolled["installation_principal"])), 2)

    def test_single_approval_cannot_enroll_wallet(self):
        action = self.make_enroll()
        with self.assertRaises(PermissionError):
            self.service.apply(action, [approval(action, self.gov1, "one")], self.policy)
        self.assertEqual(self.storage.wallet_enrollments_for_principal(installation_principal(self.issuer_b64)[0]), [])

    def test_wallet_can_be_reassigned_only_after_governed_revocation(self):
        first = self.make_enroll()
        first_enrollment = self.service.apply(first, self.approvals(first), self.policy)["enrollment"]
        revoke = self.service.build_action(
            action="WALLET_REVOKE", reason="installation key rotation",
            governance_policy_sha256=self.policy.digest,
            enrollment_id=first_enrollment["enrollment_id"],
        )
        self.service.apply(revoke, self.approvals(revoke), self.policy)
        second_key = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        second_b64 = base64.b64encode(second_key).decode()
        second = self.make_enroll(issuer=second_b64)
        second_enrollment = self.service.apply(second, self.approvals(second), self.policy)["enrollment"]
        self.assertEqual(second_enrollment["wallet_address"], first_enrollment["wallet_address"])
        self.assertNotEqual(second_enrollment["installation_principal"], first_enrollment["installation_principal"])
        self.assertEqual(first_enrollment["status"], "ACTIVE")
        self.assertEqual(self.storage.wallet_enrollment(first_enrollment["enrollment_id"])["status"], "REVOKED")

    def test_same_wallet_cannot_be_enrolled_under_two_installations_on_same_chain(self):
        first = self.make_enroll()
        self.service.apply(first, self.approvals(first), self.policy)
        second_issuer = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        second_b64 = base64.b64encode(second_issuer).decode()
        second = self.make_enroll(issuer=second_b64)
        with self.assertRaises(ValueError):
            self.service.apply(second, self.approvals(second), self.policy)
        self.assertEqual(len(self.storage.wallet_enrollment_governance_actions(installation_principal(self.issuer_b64)[0])), 1)

    def test_principal_tampering_and_invalid_finality_fail_closed(self):
        action = self.make_enroll()
        action["installation_principal"] = "anna-installation:" + "0" * 64
        with self.assertRaises(PermissionError):
            self.service.apply(action, self.approvals(action), self.policy)
        with self.assertRaises(ValueError):
            self.service.build_action(
                action="WALLET_ENROLL", reason="bad", governance_policy_sha256=self.policy.digest,
                issuer_public_key_b64=self.issuer_b64, chain_id=8453, network="base",
                wallet_address="0x" + "a" * 40, min_confirmations=0,
            )

    def test_network_name_must_match_chain_id(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.service.build_action(
                action="WALLET_ENROLL", reason="wrong network", governance_policy_sha256=self.policy.digest,
                issuer_public_key_b64=self.issuer_b64, chain_id=1, network="base",
                wallet_address="0x" + "a" * 40, min_confirmations=12,
            )

    def test_wallet_address_must_be_evm_address(self):
        with self.assertRaises(ValueError):
            self.make_enroll(wallet="not-an-address")


if __name__ == "__main__":
    unittest.main()
