"""Anna-to-Verigate capability authorization and execution-boundary tests."""
import asyncio
import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from attest.keys import load_public_key
from enforcement.evm import EVMExecutionAdapter
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = ROOT / "anna" / "executas" / "verigate-authority" / "verigate_authority_plugin.py"
SPEC = importlib.util.spec_from_file_location("anna_execution_plugin_test", PLUGIN_PATH)
plugin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(plugin)

VALID_PAYEE = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"


class FakeAPSStorage:
    """In-memory App-scope APS with ETag-checked one-time deletion."""

    def __init__(self):
        self.values = {}

    async def get(self, key, *, scope="app", timeout=10.0):
        if scope != "app":
            raise AssertionError("approval gate must use App scope")
        record = self.values.get(key)
        if record is None:
            return {"value": None, "exists": False}
        return {"value": record["value"], "etag": record["etag"], "exists": True}

    async def delete(self, key, *, scope="app", if_match=None, timeout=10.0):
        if scope != "app":
            raise AssertionError("approval gate must use App scope")
        record = self.values.get(key)
        if record is None or record["etag"] != if_match:
            return {"deleted": False}
        del self.values[key]
        return {"deleted": True}


class AnnaExecutionAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="verigate-anna-auth-")
        self.previous = os.environ.get("VERIGATE_ANNA_DATA_DIR")
        os.environ["VERIGATE_ANNA_DATA_DIR"] = self.tmp.name
        self.previous_storage = plugin._storage
        self.storage = FakeAPSStorage()
        plugin._storage = self.storage
        self.counter = 0
        if plugin._state is not None:
            plugin._state[0].storage.close()
        plugin._state = None

    def tearDown(self):
        if plugin._state is not None:
            plugin._state[0].storage.close()
        plugin._state = None
        plugin._storage = self.previous_storage
        if self.previous is None:
            os.environ.pop("VERIGATE_ANNA_DATA_DIR", None)
        else:
            os.environ["VERIGATE_ANNA_DATA_DIR"] = self.previous
        self.tmp.cleanup()

    def _nonce(self):
        self.counter += 1
        return f"{self.counter:048x}"

    def _approval(self, kind, **fields):
        nonce = self._nonce()
        now_ms = int(time.time() * 1000)
        value = {
            "version": 1,
            "kind": kind,
            "nonce": nonce,
            **fields,
            "created_at_ms": now_ms,
            "expires_at_ms": now_ms + 60_000,
        }
        self.storage.values[f"verigate/approvals/{nonce}"] = {
            "value": value,
            "etag": f"etag-{self.counter}",
        }
        return nonce

    def _args(self, **overrides):
        args = {
            "agent_id": "anna-test-agent",
            "payee": VALID_PAYEE,
            "asset": "USDC",
            "network": "base",
            "amount": 25,
            "resource": "invoice 1042",
        }
        args.update(overrides)
        return args

    def _authorize(self, **overrides):
        args = self._args(**overrides)
        normalized = {
            "agent_id": args["agent_id"].strip(),
            "payee": args["payee"].strip(),
            "asset": args["asset"].strip().upper(),
            "network": args["network"].strip().lower(),
            "amount": float(args["amount"]),
            "resource": args.get("resource", "").strip(),
        }
        args["confirmation_nonce"] = self._approval("payment_authorization", **normalized)
        return asyncio.run(plugin._verigate_authorize_payment(args))

    def _wallet_consume_args(self, authorization):
        action = authorization["payload"]["action"]
        transaction = EVMExecutionAdapter._transaction(action)
        nonce = self._approval(
            "wallet_submission",
            authorization_id=authorization["payload"]["authorization_id"],
            agent_id=action["agent_id"],
            target=action["target"],
            asset=action["asset"],
            network=action["network"],
            amount=action["amount"],
            resource=action.get("resource") or "",
            chain_id=transaction["chain_id"],
            to=transaction["to"],
            value_wei=transaction["value_wei"],
            data=transaction["data"],
        )
        return {
            "authorization_json": json.dumps(authorization),
            "confirmation_nonce": nonce,
        }

    def test_permission_requires_app_scoped_user_confirmation(self):
        args = self._args(confirmation_nonce=self._nonce())
        result = asyncio.run(plugin._verigate_authorize_payment(args))
        self.assertFalse(result["success"])
        self.assertIn("no app-scoped UI approval", result["error"])
        self.assertIsNone(plugin._state)

    def test_allow_issues_verifiable_capability_bound_permission(self):
        result = self._authorize()
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
        self.assertEqual(confirmation["source"], "anna-app-scoped-one-time-approval")

    def test_allow_binds_canonical_native_usdc_transfer_to_signed_action(self):
        result = self._authorize()
        self.assertTrue(result["success"], result)
        authorization = result["data"]["execution_authorization"]
        action = authorization["payload"]["action"]
        tx = action["metadata"]["evm_transaction"]
        self.assertEqual(tx["chain_id"], 8453)
        self.assertEqual(tx["to"].lower(), "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913")
        expected_data = (
            "0xa9059cbb"
            + ("0" * 24)
            + VALID_PAYEE[2:].lower()
            + format(25_000_000, "064x")
        )
        self.assertEqual(tx["data"], expected_data)
        self.assertEqual(tx["value_wei"], 0)

    def test_wallet_handoff_requires_separate_app_approval_and_consumes_once(self):
        result = self._authorize()
        self.assertTrue(result["success"], result)
        authorization = result["data"]["execution_authorization"]
        first = asyncio.run(plugin._verigate_consume_execution_authorization(
            self._wallet_consume_args(authorization)
        ))
        self.assertTrue(first["success"], first)
        self.assertTrue(first["data"]["consumed"])
        self.assertEqual(first["data"]["execution_status"], "CONSUMED_AWAITING_WALLET")
        self.assertFalse(first["data"]["transaction_submitted"])
        self.assertEqual(first["data"]["transaction"]["chain_id"], 8453)

        # A fresh UI approval cannot replay an authorization already consumed by ExecutionRouter.
        replay = asyncio.run(plugin._verigate_consume_execution_authorization(
            self._wallet_consume_args(authorization)
        ))
        self.assertFalse(replay["success"])
        self.assertIn("already consumed", replay["error"])

    def test_warn_and_block_never_get_execution_authority(self):
        warn = self._authorize(amount=300)
        self.assertTrue(warn["success"], warn)
        self.assertEqual(warn["data"]["decision_receipt"]["payload"]["decision"]["decision"], "WARN")
        self.assertIsNone(warn["data"]["execution_authorization"])
        block = self._authorize(amount=600)
        self.assertTrue(block["success"], block)
        self.assertEqual(block["data"]["decision_receipt"]["payload"]["decision"]["decision"], "BLOCK")
        self.assertIsNone(block["data"]["execution_authorization"])

    def test_router_consumes_anna_authorization_once_before_side_effect(self):
        result = self._authorize()
        self.assertTrue(result["success"], result)
        authorization = result["data"]["execution_authorization"]
        engine, _ = plugin._get_state()
        public_key = load_public_key(Path(self.tmp.name) / "issuer.pub")
        router = ExecutionRouter(NetworkRegistry(), engine.storage, public_key)
        calls = []
        result = router.execute(authorization, lambda exact_action: calls.append(exact_action) or "mock-tx")
        self.assertEqual(result, "mock-tx")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["chain_id"], 8453)
        self.assertEqual(calls[0]["value_wei"], 0)
        self.assertIn(VALID_PAYEE[2:].lower(), calls[0]["data"].lower())
        with self.assertRaises(PermissionError):
            router.execute(authorization, lambda exact_action: calls.append(exact_action) or "replay")
        self.assertEqual(len(calls), 1)

    def test_tampered_action_is_rejected_before_executor_callback(self):
        result = self._authorize()
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
