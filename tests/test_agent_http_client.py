import json
import unittest
from io import BytesIO
from urllib.error import HTTPError, URLError
from unittest.mock import patch

from integrations.http_client import (
    VerigateAPIError,
    VerigateClient,
    VerigateTransportError,
)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.raw = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.raw


class AgentHttpClientTest(unittest.TestCase):
    def test_authorize_action_posts_signed_intent_with_auth_and_tenant_headers(self):
        response = {
            "decision_receipt": {"payload": {"decision": "ALLOW"}},
            "execution_authorization": {"payload": {}},
        }
        with patch("integrations.http_client.urlopen", return_value=FakeResponse(response)) as open_url:
            client = VerigateClient(
                "https://api.example/",
                api_key="secret",
                tenant_id="tenant-a",
                timeout=3,
            )
            result = client.authorize_action({"agent_id": "agent-1", "agent_signature": "sig"})
        self.assertEqual(result, response)
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.example/v1/actions/authorize")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(request.get_header("X-verigate-tenant"), "tenant-a")
        self.assertEqual(json.loads(request.data), {"agent_id": "agent-1", "agent_signature": "sig"})
        self.assertEqual(open_url.call_args.kwargs["timeout"], 3.0)

    def test_consume_wraps_authorization_in_expected_envelope(self):
        authorization = {"payload": {"authorization_id": "auth-1"}, "signature": "sig"}
        with patch(
            "integrations.http_client.urlopen",
            return_value=FakeResponse({"execute": True, "reason": "consumed"}),
        ) as open_url:
            result = VerigateClient("http://localhost:8000").consume_execution(authorization)
        self.assertTrue(result["execute"])
        request = open_url.call_args.args[0]
        self.assertEqual(request.full_url, "http://localhost:8000/v1/execution/consume")
        self.assertEqual(json.loads(request.data), {"authorization": authorization})

    def test_authorize_and_consume_does_not_consume_when_no_authorization_is_issued(self):
        denied = {
            "decision_receipt": {"payload": {"decision": "BLOCK"}},
            "execution_authorization": None,
        }
        with patch("integrations.http_client.urlopen", return_value=FakeResponse(denied)) as open_url:
            result = VerigateClient("http://localhost").authorize_and_consume({"agent_id": "agent"})
        self.assertFalse(result["authorized"])
        self.assertIsNone(result["consumption"])
        open_url.assert_called_once()

    def test_api_error_preserves_status_and_detail(self):
        error = HTTPError(
            "https://api.example/v1/actions/authorize",
            403,
            "Forbidden",
            {},
            BytesIO(b'{"detail":"agent signature rejected"}'),
        )
        with patch("integrations.http_client.urlopen", side_effect=error):
            with self.assertRaises(VerigateAPIError) as caught:
                VerigateClient("https://api.example").authorize_action({})
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.detail, "agent signature rejected")

    def test_transport_error_is_explicit(self):
        with patch("integrations.http_client.urlopen", side_effect=URLError("offline")):
            with self.assertRaises(VerigateTransportError):
                VerigateClient("https://api.example").authorize_action({})

    def test_rejects_invalid_configuration_and_non_dict_authorization(self):
        with self.assertRaises(ValueError):
            VerigateClient("api.example")
        with self.assertRaises(ValueError):
            VerigateClient("https://api.example", timeout=0)
        with self.assertRaises(TypeError):
            VerigateClient("https://api.example").consume_execution("not-a-dict")


if __name__ == "__main__":
    unittest.main()
