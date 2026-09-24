import hashlib
import unittest

from enforcement.external_state_http import HTTPExternalStateVerifier


def digest(observation):
    import json
    return hashlib.sha256(json.dumps(observation, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


class HTTPExternalStateTest(unittest.TestCase):
    def binding(self, body=b'{"version":7}'):
        obs={"kind":"http.state","url":"https://api.test/orders/1","method":"GET","status":200,"etag":"\"v7\"","response_sha256":hashlib.sha256(body).hexdigest()}
        return {**obs, "reference":"order-1", "digest":digest(obs)}

    def test_matching_etag_and_body(self):
        body=b'{"version":7}'
        binding=self.binding(body)
        transport=lambda u,m,h:(200,{"etag":"\"v7\""},body)
        ok,reason=HTTPExternalStateVerifier(transport)(binding,{})
        self.assertTrue(ok,reason)

    def test_etag_drift_blocks(self):
        binding=self.binding()
        transport=lambda u,m,h:(200,{"etag":"\"v8\""},b'{"version":7}')
        ok,reason=HTTPExternalStateVerifier(transport)(binding,{})
        self.assertFalse(ok); self.assertIn("ETag",reason)

    def test_body_drift_blocks(self):
        binding=self.binding()
        transport=lambda u,m,h:(200,{"etag":"\"v7\""},b'{"version":8}')
        ok,reason=HTTPExternalStateVerifier(transport)(binding,{})
        self.assertFalse(ok); self.assertIn("response digest",reason)

    def test_status_drift_blocks(self):
        binding=self.binding()
        transport=lambda u,m,h:(404,{},b'')
        ok,reason=HTTPExternalStateVerifier(transport)(binding,{})
        self.assertFalse(ok); self.assertIn("status changed",reason)


if __name__ == "__main__": unittest.main()
