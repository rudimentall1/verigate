"""The product's central claim is that a third party can verify a signed
decision using only what /v1/check gave them -- no server access. This
guards that end to end, through the real HTTP response, not internals.
"""
import unittest

from fastapi.testclient import TestClient

from api import main
from api.main import app

PAYMENT = {
    "agent_id": "agent-1",
    "payee": "0xMerchant123",
    "asset": "USDC",
    "network": "base",
    "amount": 1.0,
    "sign": True,
}


class AttestationVerificationTest(unittest.TestCase):
    def setUp(self):
        self._old_policy_path = main.POLICY_PATH
        main.POLICY_PATH = "policies/default.yaml"

    def tearDown(self):
        main.POLICY_PATH = self._old_policy_path

    def test_check_response_is_independently_verifiable_via_v1_verify(self):
        # Regression: DecisionResponse used to omit context_sha256, so the
        # payload FastAPI actually returned never matched what was signed
        # -- every genuine attestation failed its own verification.
        with TestClient(app) as client:
            resp = client.post("/v1/check", json=PAYMENT)
            self.assertEqual(resp.status_code, 200)
            attestation = resp.json()
            self.assertIn("context_sha256", attestation["payload"])
            verify_resp = client.post("/v1/verify", json=attestation)
        self.assertEqual(verify_resp.status_code, 200)
        self.assertTrue(verify_resp.json()["valid"], verify_resp.json())

    def test_tampered_response_fails_verification(self):
        with TestClient(app) as client:
            resp = client.post("/v1/check", json=PAYMENT)
            attestation = resp.json()
            attestation["payload"]["decision"] = (
                "ALLOW" if attestation["payload"]["decision"] != "ALLOW" else "BLOCK"
            )
            verify_resp = client.post("/v1/verify", json=attestation)
        self.assertFalse(verify_resp.json()["valid"])


if __name__ == "__main__":
    unittest.main()
