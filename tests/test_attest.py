import os
import tempfile
import unittest

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.sign import sign_decision
from attest.verify import verify_attestation
from core.models import Decision, GuardrailDecision, RuleMatch, Severity


class AttestTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.priv_path = os.path.join(self.tmpdir, "issuer.key")
        self.pub_path = os.path.join(self.tmpdir, "issuer.pub")
        generate_keypair(self.priv_path, self.pub_path)
        self.decision = GuardrailDecision(
            intent_id="intent-123",
            agent_id="agent-1",
            decision=Decision.ALLOW,
            matched_rules=(),
        )

    def test_sign_then_verify_succeeds(self):
        priv = load_private_key(self.priv_path)
        pub = load_public_key(self.pub_path)

        attestation = sign_decision(self.decision, priv)
        ok, reason = verify_attestation(attestation.as_dict(), pub)

        self.assertTrue(ok, reason)

    def test_tampered_payload_fails_verification(self):
        priv = load_private_key(self.priv_path)
        pub = load_public_key(self.pub_path)

        attestation = sign_decision(self.decision, priv).as_dict()
        # Attacker flips BLOCK's decision to ALLOW after the fact.
        attestation["payload"]["decision"] = "ALLOW" if attestation["payload"]["decision"] != "ALLOW" else "BLOCK"

        ok, reason = verify_attestation(attestation, pub)
        self.assertFalse(ok)
        self.assertIn("tampered", reason)

    def test_wrong_public_key_fails_verification(self):
        priv = load_private_key(self.priv_path)
        other_pub_path = os.path.join(self.tmpdir, "other.pub")
        other_priv_path = os.path.join(self.tmpdir, "other.key")
        generate_keypair(other_priv_path, other_pub_path)
        wrong_pub = load_public_key(other_pub_path)

        attestation = sign_decision(self.decision, priv).as_dict()
        ok, reason = verify_attestation(attestation, wrong_pub)
        self.assertFalse(ok)

    def test_verification_needs_no_server_access(self):
        """The whole point: verification is a pure function of
        (attestation, public_key). No network, no database, no issuer."""
        priv = load_private_key(self.priv_path)
        pub = load_public_key(self.pub_path)
        decision = GuardrailDecision(
            intent_id="intent-999",
            agent_id="agent-2",
            decision=Decision.BLOCK,
            matched_rules=(RuleMatch("blocked_payee", Severity.BLOCK, "on blocklist"),),
        )
        attestation = sign_decision(decision, priv).as_dict()
        del priv  # simulate: verifier has no relationship with the issuer's process
        ok, _ = verify_attestation(attestation, pub)
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
