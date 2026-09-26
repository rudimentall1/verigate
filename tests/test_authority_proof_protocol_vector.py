from __future__ import annotations

import base64
import json
import unittest
from pathlib import Path

from core.proof_package import parse_proof_package, verify_proof_package

ROOT = Path(__file__).resolve().parents[1]
VECTOR = ROOT / "examples" / "authority-proof" / "authority-proof.json"
KEY = ROOT / "examples" / "authority-proof" / "issuer.pub"


class AuthorityProofProtocolVectorTests(unittest.TestCase):
    def test_reference_vector_matches_protocol(self) -> None:
        package = VECTOR.read_bytes()
        pem = KEY.read_bytes()
        from cryptography.hazmat.primitives import serialization
        public_key = serialization.load_pem_public_key(pem)
        raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        trusted = base64.b64encode(raw).decode("ascii")
        result = verify_proof_package(package, trusted_public_key_b64=trusted)
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["proof_protocol"], "verigate-authority-proof-v1")
        self.assertEqual(result["checks"]["authority_protocol"]["details"]["assertion_count"], 9)
        parsed = parse_proof_package(package)
        executed_at = next(n for n in parsed["package"]["manifest"]["payload"]["nodes"] if n["type"] == "execution_receipt")["data"]["payload"]["executed_at"]
        self.assertEqual(result["checks"]["execution_authorization"]["historical_verification_time"], executed_at)

    def test_reference_vector_rejects_package_mutation(self) -> None:
        document = json.loads(VECTOR.read_text(encoding="utf-8"))
        document["package"]["agent_id"] = "tampered-agent"
        result = verify_proof_package(json.dumps(document).encode(), trusted_public_key_b64=None)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "proof package digest mismatch")


if __name__ == "__main__":
    unittest.main()
