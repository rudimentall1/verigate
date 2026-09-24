import unittest

from core.effect_verification import HTTPResponseVerifier, MCPToolVerifier, digest


class EffectVerificationTest(unittest.TestCase):
    def setUp(self):
        self.http_auth = {"payload": {"authorization_id": "auth-http", "action_sha256": "a" * 64, "action": {"action_type": "api.request", "target": "https://api.example.test/items", "metadata": {"method": "POST", "url": "https://api.example.test/items"}}}}
        self.mcp_auth = {"payload": {"authorization_id": "auth-mcp", "action_sha256": "b" * 64, "action": {"action_type": "mcp.tool.call", "target": "orders.create"}}}

    def test_http_response_is_bound_to_authorized_request(self):
        observed = HTTPResponseVerifier().verify_response(
            self.http_auth,
            {"url": "https://api.example.test/items", "method": "POST", "status_code": 201, "headers": {"x-request-id": "r1"}, "body": {"id": 7}},
            evidence_ref="https://api.example.test/observations/r1",
            observed_at=100.0,
        )
        self.assertEqual(observed.effect_status, "SUCCEEDED")
        self.assertEqual(observed.authorization_id, "auth-http")
        self.assertEqual(observed.action_sha256, "a" * 64)
        self.assertEqual(observed.evidence_kind, "HTTP_RESPONSE")
        self.assertEqual(observed.as_dict()["observation"]["body_sha256"], digest({"id": 7}))

    def test_http_drift_fails_closed(self):
        with self.assertRaises(ValueError):
            HTTPResponseVerifier().verify_response(
                self.http_auth,
                {"url": "https://evil.example.test/items", "method": "POST", "status_code": 201, "headers": {}, "body": {}},
                evidence_ref="drift",
            )

    def test_mcp_result_is_bound_to_authorized_tool(self):
        observed = MCPToolVerifier().verify_result(
            self.mcp_auth,
            tool_name="orders.create",
            result={"order_id": "o-1", "status": "created"},
            evidence_ref="mcp://orders.create/o-1",
            target_identity="orders-service",
            observed_at=101.0,
        )
        self.assertEqual(observed.effect_status, "SUCCEEDED")
        self.assertEqual(observed.observation["tool_name"], "orders.create")
        self.assertEqual(observed.observation["target_identity"], "orders-service")

    def test_mcp_target_swap_fails_closed(self):
        with self.assertRaises(ValueError):
            MCPToolVerifier().verify_result(
                self.mcp_auth,
                tool_name="orders.delete",
                result={"ok": True},
                evidence_ref="mcp://orders.delete/1",
            )


if __name__ == "__main__":
    unittest.main()
