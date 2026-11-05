"""Anna-to-Verigate capability authorization and execution-boundary tests."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

from attest.keys import load_public_key
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = ROOT / "anna" / "executas" / "verigate-authority" / "verigate_authority_plugin.py"
SPEC = importlib.util.spec_from_file_location("anna_execution_plugin_test", PLUGIN_PATH)
plugin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plugin)

VALID_PAYEE = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"


class AnnaExecutionAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="verigate-anna-auth-")
        self.previous = os.environ.get("VERIGATE_ANNA_DATA_DIR")
        os.environ["VERIGATE_ANNA_DATA_DIR"] = self.tmp.name
        if plugin._state is not None:
            plugin._state[0].storage.close()
        plugin._state = None

    def tearDown(self):
        if plugin._state is not None:
            plugin._state[0].storage.close()
        plugin._state = None
        if self.previous is None:
            os.environ.pop("VERIGATE_ANNA_DATA_DIR", None)
        else:
            os.environ["VERIGATE_ANNA_DATA_DIR"] = self.previous
        self.tmp.cleanup()

    def _args(self, **overrides):
        args = {
            "agent_id": "anna-test-agent",
            "payee": VALID_PAYEE,
            "asset": "USDC",
            "network": "base",
            "amount": 25,
            "resource": "invoice 1042",
            "human_confirmed": True,
        }
        args.update(overrides)
        return args

    def test_permission_requires_explicit_user_confirmation(self):
        result = plugin._verigate_authorize_payment(self._args(human_confirmed=False))
        self.assertFalse(result["success"])
        self.assertIn("explicit user confirmation", result["error"])
        self.assertIsNone(plugin._state)

    def test_allow_issues_verifiable_capability_bound_permission(self):
        result = plugin._verigate_authorize_payment(self._args())
        self.assertTrue(result["success"], result)
        data = result["data"]
        self.assertEqual(data["decision_receipt"]["payload"]["decision"]["decision"], "ALLOW")
        self.assertEqual(data["execution_status"], "ISSUED")
        authorization = data["execution_authorization"]
        self.assertIsNotNone(authorization)
        verified = plugin._verigate_verify_execution_authorization({
            "authorization_json": json.dumps(authorization)
        })
        self.assertTrue(verified["data"]["verified"], verified)
        self.assertFalse(verified["data"]["consumed"])
        self.assertFalse(verified["data"]["transaction_submitted"])
        self.assertEqual(verified["data"]["action"]["target"], VALID_PAYEE)
        self.assertEqual(verified["data"]["action"]["amount"], 25)
        confirmation = verified["data"]["action"]["metadata"]["anna_user_confirmation"]
        self.assertTrue(confirmation["confirmed"])
        self.assertEqual(confirmation["source"], "anna-app-confirmation-button")

    def test_warn_and_block_never_get_execution_authority(self):
        warn = plugin._verigate_authorize_payment(self._args(amount=300))
        self.assertTrue(warn["success"], warn)
        self.assertEqual(warn["data"]["decision_receipt"]["payload"]["decision"]["decision"], "WARN")
        self.assertIsNone(warn["data"]["execution_authorization"])
        block = plugin._verigate_authorize_payment(self._args(amount=600))
        self.assertTrue(block["success"], block)
        self.assertEqual(block["data"]["decision_receipt"]["payload"]["decision"]["decision"], "BLOCK")
        self.assertIsNone(block["data"]["execution_authorization"])

    def test_router_consumes_anna_authorization_once_before_side_effect(self):
        result = plugin._verigate_authorize_payment(self._args())
        self.assertTrue(result["success"], result)
        authorization = result["data"]["execution_authorization"]
        engine, _ = plugin._get_state()
        public_key = load_public_key(Path(self.tmp.name) / "issuer.pub")
        router = ExecutionRouter(NetworkRegistry(), engine.storage, public_key)
        calls = []
        action = router.execute(authorization, lambda exact_action: calls.append(exact_action) or "mock-tx")
        self.assertEqual(action, "mock-tx")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["target"], VALID_PAYEE)
        with self.assertRaises(PermissionError):
            router.execute(authorization, lambda exact_action: calls.append(exact_action) or "replay")
        self.assertEqual(len(calls), 1)

    def test_tampered_action_is_rejected_before_executor_callback(self):
        result = plugin._verigate_authorize_payment(self._args())
        self.assertTrue(result["success"], result)
        authorization = result["data"]["execution_authorization"]
        authorization["payload"]["action"]["target"] = "0xAttacker"
        engine, _ = plugin._get_state()
        public_key = load_public_key(Path(self.tmp.name) / "issuer.pub")
        router = ExecutionRouter(NetworkRegistry(), engine.storage, public_key)
        calls = []
        with self.assertRaises((PermissionError, ValueError)):
            router.execute(authorization, lambda exact_action: calls.append(exact_action) or "bad")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
