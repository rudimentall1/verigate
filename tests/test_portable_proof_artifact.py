import base64
import json
import unittest
from pathlib import Path

from attest.keys import load_public_key
from cryptography.hazmat.primitives import serialization
from core.proof_package import verify_proof_package


class CheckedInPortableProofTests(unittest.TestCase):
    def test_checked_in_authority_proof_is_independently_verifiable(self):
        root = Path(__file__).resolve().parents[1]
        proof = root / "examples" / "authority-proof" / "authority-proof.json"
        public_key = root / "examples" / "authority-proof" / "issuer.pub"
        package = json.loads(proof.read_text(encoding="utf-8"))
        key = load_public_key(public_key)
        trusted = base64.b64encode(
            key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        ).decode("ascii")

        result = verify_proof_package(proof.read_bytes(), trusted_public_key_b64=trusted)
        self.assertTrue(result["valid"], result)
        self.assertTrue(result["package_valid"])
        self.assertEqual(
            package["package"]["manifest"]["issuer_public_key_b64"],
            trusted,
        )
        self.assertEqual(result["proof_protocol"], "verigate-authority-proof-v1")
        self.assertEqual(result["checks"]["authority_protocol"]["details"]["assertion_count"], 9)


if __name__ == "__main__":
    unittest.main()
