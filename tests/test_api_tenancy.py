import base64
import json
import os
import tempfile
import unittest

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi.testclient import TestClient

from api import main
from api.main import app
from api.tenancy import TENANT_HEADER

ENV = ("VERIGATE_TENANT_KEY_DIR", "VERIGATE_KEY_PASSPHRASE")
PAYMENT = {
    "agent_id": "agent-1",
    "payee": "0xMerchant123",
    "asset": "USDC",
    "network": "base",
    "amount": 1.0,
    "sign": True,
}


def _load_pubkey(pem: str) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem.encode("ascii"))
    assert isinstance(key, Ed25519PublicKey)
    return key


def _verifies(public_key: Ed25519PublicKey, signature: bytes, message: bytes) -> bool:
    try:
        public_key.verify(signature, message)
        return True
    except InvalidSignature:
        return False


def _canonical_signed_bytes(attestation: dict) -> bytes:
    # Match attest.sign.canonical_payload exactly: it signs only the inner
    # decision payload, not the outer {"payload","signature","algorithm"}.
    return json.dumps(attestation["payload"], sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


class ApiTenancyTest(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.pop(k, None) for k in ENV}
        # Several other test modules point api.main.POLICY_PATH at their
        # own tempdir and never restore it, so by discovery order this
        # module can inherit a POLICY_PATH pointing at an already-deleted
        # directory. Pin it back before starting the app here.
        self._old_policy_path = main.POLICY_PATH
        main.POLICY_PATH = "policies/default.yaml"

    def tearDown(self):
        main.POLICY_PATH = self._old_policy_path
        for k, v in self._saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    def test_without_tenant_dir_configured_behavior_is_unchanged(self):
        # No VERIGATE_TENANT_KEY_DIR: the tenant header must be a no-op.
        with TestClient(app) as client:
            default_key = client.get("/v1/public-key").text
            tenant_a_key = client.get(
                "/v1/public-key", headers={TENANT_HEADER: "tenant-a"}
            ).text
        self.assertEqual(default_key, tenant_a_key)

    def test_each_tenant_gets_its_own_key_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["VERIGATE_TENANT_KEY_DIR"] = tmp
            with TestClient(app) as client:
                key_a = client.get(
                    "/v1/public-key", headers={TENANT_HEADER: "tenant-a"}
                ).text
                key_b = client.get(
                    "/v1/public-key", headers={TENANT_HEADER: "tenant-b"}
                ).text
            self.assertNotEqual(key_a, key_b)

    def test_attestation_signature_verifies_only_against_its_own_tenant(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["VERIGATE_TENANT_KEY_DIR"] = tmp
            with TestClient(app) as client:
                resp_a = client.post(
                    "/v1/check", json=PAYMENT, headers={TENANT_HEADER: "tenant-a"}
                )
                self.assertEqual(resp_a.status_code, 200)
                attestation = resp_a.json()
                signature = base64.b64decode(attestation["signature"])
                payload_bytes = _canonical_signed_bytes(attestation)

                pub_a = _load_pubkey(
                    client.get(
                        "/v1/public-key", headers={TENANT_HEADER: "tenant-a"}
                    ).text
                )
                pub_b = _load_pubkey(
                    client.get(
                        "/v1/public-key", headers={TENANT_HEADER: "tenant-b"}
                    ).text
                )

            verified_with_a = _verifies(pub_a, signature, payload_bytes)
            verified_with_b = _verifies(pub_b, signature, payload_bytes)
            self.assertTrue(verified_with_a, "tenant-a's own key must verify its signature")
            self.assertFalse(verified_with_b, "tenant-b's key must NOT verify tenant-a's signature")

    def test_governance_public_key_is_not_affected_by_tenant_header(self):
        # Governance is a shared authority across all tenants by design.
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["VERIGATE_TENANT_KEY_DIR"] = tmp
            with TestClient(app) as client:
                gov_a = client.get(
                    "/v1/governance/public-key", headers={TENANT_HEADER: "tenant-a"}
                ).text
                gov_b = client.get(
                    "/v1/governance/public-key", headers={TENANT_HEADER: "tenant-b"}
                ).text
            self.assertEqual(gov_a, gov_b)


if __name__ == "__main__":
    unittest.main()
