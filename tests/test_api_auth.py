import hashlib
import os
import unittest

from fastapi.testclient import TestClient

from api.auth import PUBLIC_ROUTES
from api.main import app


class ApiAuthTest(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("VERIGATE_API_KEYS", "VERIGATE_REQUIRE_AUTH")}
        self.client = TestClient(app)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_protected_route_rejects_missing_and_wrong_key(self):
        os.environ["VERIGATE_API_KEYS"] = "secret-one"
        self.assertEqual(self.client.get("/v1/execution/networks").status_code, 401)
        r = self.client.get("/v1/execution/networks", headers={"Authorization": "Bearer nope"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.client.post("/v1/authorize", json={}).status_code, 401)

    def test_valid_key_passes_auth_layer(self):
        os.environ["VERIGATE_API_KEYS"] = "secret-one,secret-two"
        for headers in ({"Authorization": "Bearer secret-two"}, {"X-API-Key": "secret-one"}):
            r = self.client.get("/v1/execution/networks", headers=headers)
            self.assertNotEqual(r.status_code, 401)

    def test_hashed_key_entry(self):
        os.environ["VERIGATE_API_KEYS"] = "sha256:" + hashlib.sha256(b"abc123").hexdigest()
        self.assertNotEqual(
            self.client.get("/v1/execution/networks", headers={"X-API-Key": "abc123"}).status_code, 401)
        self.assertEqual(
            self.client.get("/v1/execution/networks", headers={"X-API-Key": "abc124"}).status_code, 401)

    def test_public_routes_stay_open(self):
        os.environ["VERIGATE_API_KEYS"] = "secret-one"
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertNotEqual(self.client.post("/v1/verify", json={}).status_code, 401)
        self.assertEqual(len(PUBLIC_ROUTES), 5)

    def test_require_auth_without_keys_fails_closed(self):
        os.environ.pop("VERIGATE_API_KEYS", None)
        os.environ["VERIGATE_REQUIRE_AUTH"] = "1"
        self.assertEqual(self.client.get("/v1/execution/networks").status_code, 401)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_malformed_hash_entry_never_matches_and_never_opens_api(self):
        # Regression: a typo'd key list must lock the API, not open it.
        os.environ["VERIGATE_API_KEYS"] = "sha256:zzzz"
        self.assertEqual(
            self.client.get("/v1/execution/networks", headers={"X-API-Key": "zzzz"}).status_code, 401)
        self.assertEqual(self.client.get("/v1/execution/networks").status_code, 401)


if __name__ == "__main__":
    unittest.main()
