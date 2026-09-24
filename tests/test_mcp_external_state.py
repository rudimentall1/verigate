import unittest

from enforcement.external_state_mcp import MCPExternalStateVerifier
from core.external_state import external_state_digest_from_observation


class MCPExternalStateTest(unittest.TestCase):
    def binding(self, observation):
        return {"kind":"mcp.state","tool":"orders.create","reference":"order-1","digest":external_state_digest_from_observation(observation)}

    def test_matching_state(self):
        state={"version":7,"status":"pending"}
        provider=lambda tool,ref,binding: state
        ok,reason=MCPExternalStateVerifier(provider)(self.binding(state),{"action_type":"mcp.tool.call","target":"orders.create"})
        self.assertTrue(ok,reason)

    def test_state_drift_blocks(self):
        state={"version":7,"status":"pending"}
        provider=lambda tool,ref,binding: {"version":8,"status":"pending"}
        ok,reason=MCPExternalStateVerifier(provider)(self.binding(state),{"action_type":"mcp.tool.call","target":"orders.create"})
        self.assertFalse(ok); self.assertIn("digest changed",reason)

    def test_target_drift_blocks(self):
        state={"version":7}
        ok,reason=MCPExternalStateVerifier(lambda *args:state)(self.binding(state),{"action_type":"mcp.tool.call","target":"orders.delete"})
        self.assertFalse(ok); self.assertIn("authorized target",reason)

    def test_provider_failure_fails_closed(self):
        state={"version":7}
        def provider(*args): raise RuntimeError("MCP unavailable")
        ok,reason=MCPExternalStateVerifier(provider)(self.binding(state),{"action_type":"mcp.tool.call","target":"orders.create"})
        self.assertFalse(ok); self.assertIn("verification failed",reason)


if __name__ == "__main__": unittest.main()
