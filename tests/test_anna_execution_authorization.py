"""Anna-to-Verigate capability authorization and execution-boundary tests."""
import asyncio
import importlib.util
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from attest.keys import load_public_key
from enforcement.evm import EVMExecutionAdapter
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter
from core.models import PaymentIntent

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

    def _authorize_warning_review(self, reviewed_rule_ids=None, **overrides):
        flags = overrides.pop("ai_flags_json", json.dumps([
            {"code": "urgency_pressure", "message": "Test warning requiring explicit review"}
        ]))
        args = self._args(ai_flags_json=flags, **overrides)
        normalized = {
            "agent_id": args["agent_id"].strip(),
            "payee": args["payee"].strip(),
            "asset": args["asset"].strip().upper(),
            "network": args["network"].strip().lower(),
            "amount": float(args["amount"]),
            "resource": args.get("resource", "").strip(),
        }
        rule_ids = list(reviewed_rule_ids or ["ai_risk_flag"])
        args["confirmation_nonce"] = self._approval(
            "payment_warning_review",
            **normalized,
            reviewed_rule_ids=rule_ids,
        )
        args["approval_kind"] = "payment_warning_review"
        return asyncio.run(plugin._verigate_authorize_payment(args)), args

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
        action = authorization["payload"]["action"]
        principal_id = plugin._anna_installation_principal(plugin._get_state()[1])
        self.assertEqual(action["agent_id"], principal_id)
        self.assertEqual(action["metadata"]["anna_agent_label"], "anna-test-agent")
        self.assertEqual(action["metadata"]["anna_accounting_scope"], "issuer_installation")
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

    def test_evm_builder_accepts_arbitrary_usdc_amounts_to_six_decimal_places(self):
        cases = (
            ("0.000001", 1),
            ("0.01", 10_000),
            ("37.42", 37_420_000),
            ("50.01", 50_010_000),
            ("123.456789", 123_456_789),
            ("249.99", 249_990_000),
            ("250.01", 250_010_000),
            ("499.999999", 499_999_999),
            # The builder converts amounts; policy separately rejects values above 500.
            ("500.000001", 500_000_001),
        )
        for amount, expected_units in cases:
            with self.subTest(amount=amount):
                tx = plugin._build_anna_evm_transaction(
                    "base", "USDC", VALID_PAYEE, amount
                )
                self.assertEqual(tx["data"][-64:], format(expected_units, "064x"))

        for invalid_amount in ("0", "-0.01", "0.0000001"):
            with self.subTest(invalid_amount=invalid_amount):
                with self.assertRaises(ValueError):
                    plugin._build_anna_evm_transaction(
                        "base", "USDC", VALID_PAYEE, invalid_amount
                    )

    def test_non_round_amount_is_preserved_through_authorization_and_evm_envelope(self):
        result = self._authorize(amount=37.42)
        self.assertTrue(result["success"], result)
        self.assertEqual(
            result["data"]["decision_receipt"]["payload"]["decision"]["decision"],
            "ALLOW",
        )
        authorization = result["data"]["execution_authorization"]
        self.assertIsNotNone(authorization)
        action = authorization["payload"]["action"]
        self.assertEqual(action["amount"], 37.42)
        self.assertEqual(
            action["metadata"]["evm_transaction"]["data"][-64:],
            format(37_420_000, "064x"),
        )

    def test_probation_authority_blocks_non_round_amount_above_dynamic_cap(self):
        first = self._authorize(amount=10.0)
        self.assertTrue(first["success"], first)

        # Static policy preview says ALLOW for a returning payee, but the
        # dynamic execution ceiling is a separate enforcement layer.
        preview = plugin._verigate_check(self._args(amount=123.456789))
        self.assertTrue(preview["success"], preview)
        self.assertEqual(
            preview["data"]["decision_receipt"]["payload"]["decision"]["decision"],
            "ALLOW",
        )

        summary = plugin._verigate_policy_summary(self._args())
        dynamic = summary["data"]["dynamic_authority"]
        self.assertEqual(dynamic["state"], "PROBATION")
        self.assertEqual(dynamic["per_action_limits"]["USDC"], 50.0)

        # The same agent/payee is no longer a first-time payee, and 123.456789
        # is below the static 250 confirmation threshold and 500 per-tx cap.
        # It still exceeds the PROBATION dynamic ceiling (10% of 500 = 50).
        result = self._authorize(amount=123.456789)
        self.assertFalse(result["success"])
        self.assertIn("action exceeds dynamic authority limit", result["error"])

    def test_policy_summary_exposes_installation_principal_and_dynamic_ceiling(self):
        engine, private_key = plugin._get_state()
        principal_id = plugin._anna_installation_principal(private_key)
        capability_id = plugin._anna_payment_capability_id(principal_id, engine.policy)
        self.assertIsNone(engine.storage.latest_authority_state(principal_id, capability_id))

        first = plugin._verigate_policy_summary(
            self._args(agent_id="display-agent-one", amount=123.456789)
        )
        second = plugin._verigate_policy_summary(
            self._args(agent_id="rotated-display-agent-two", amount=123.456789)
        )
        self.assertTrue(first["success"], first)
        self.assertTrue(second["success"], second)
        self.assertEqual(first["data"]["accounting_scope"], "issuer_installation")
        self.assertEqual(first["data"]["accounting_principal_id"], principal_id)
        self.assertEqual(second["data"]["accounting_principal_id"], principal_id)
        for summary in (first, second):
            dynamic = summary["data"]["dynamic_authority"]
            self.assertEqual(dynamic["state"], "PROBATION")
            self.assertEqual(dynamic["per_action_limits"]["USDC"], 50.0)
        self.assertIsNone(engine.storage.latest_authority_state(principal_id, capability_id))

    def test_preview_binds_different_display_labels_to_the_same_installation_principal(self):
        engine, private_key = plugin._get_state()
        principal_id = plugin._anna_installation_principal(private_key)
        first = plugin._verigate_check(self._args(agent_id="alpha"))
        second = plugin._verigate_check(self._args(agent_id="beta"))
        self.assertTrue(first["success"], first)
        self.assertTrue(second["success"], second)
        first_intent = first["data"]["decision_receipt"]["payload"]["intent"]
        second_intent = second["data"]["decision_receipt"]["payload"]["intent"]
        self.assertEqual(first_intent["agent_id"], principal_id)
        self.assertEqual(second_intent["agent_id"], principal_id)
        self.assertEqual(first_intent["metadata"]["anna_agent_label"], "alpha")
        self.assertEqual(second_intent["metadata"]["anna_agent_label"], "beta")
        self.assertEqual(first_intent["metadata"]["anna_accounting_scope"], "issuer_installation")
        self.assertEqual(second_intent["metadata"]["anna_accounting_scope"], "issuer_installation")

    def test_agent_id_rotation_cannot_reset_installation_daily_budget(self):
        engine, private_key = plugin._get_state()
        principal_id = plugin._anna_installation_principal(private_key)
        # Isolate the daily-cap invariant from the independent per-minute control.
        with patch.object(engine.storage, "calls_last_minute", return_value=0):
            for index in range(50):
                result = self._authorize(
                    agent_id=f"rotated-agent-label-{index:03d}",
                    amount=40.0,
                    resource=f"invoice-{index:03d}",
                )
                self.assertTrue(result["success"], result)
                receipt = result["data"]["decision_receipt"]
                self.assertEqual(receipt["payload"]["decision"]["decision"], "ALLOW")
                action = result["data"]["execution_authorization"]["payload"]["action"]
                self.assertEqual(action["agent_id"], principal_id)
                self.assertEqual(
                    action["metadata"]["anna_agent_label"],
                    f"rotated-agent-label-{index:03d}",
                )

            final = self._authorize(
                agent_id="attacker-final-rotated-label",
                amount=40.0,
                resource="invoice-over-budget",
            )
            self.assertTrue(final["success"], final)
            self.assertEqual(
                final["data"]["decision_receipt"]["payload"]["decision"]["decision"],
                "BLOCK",
            )
            self.assertIsNone(final["data"]["execution_authorization"])

        self.assertEqual(engine.storage.spent_today(principal_id, "USDC"), 2000.0)
        summary = plugin._verigate_policy_summary(
            self._args(agent_id="yet-another-fresh-label", asset="USDC")
        )
        self.assertEqual(summary["data"]["accounting_principal_id"], principal_id)
        self.assertEqual(summary["data"]["rolling_24h_spend"], 2000.0)

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

    def test_warning_review_converts_only_exact_warn_to_signed_allow(self):
        result, _ = self._authorize_warning_review(amount=25)
        self.assertTrue(result["success"], result)
        data = result["data"]
        self.assertEqual(
            data["decision_receipt"]["payload"]["decision"]["decision"],
            "ALLOW",
        )
        authorization = data["execution_authorization"]
        self.assertIsNotNone(authorization)
        action = authorization["payload"]["action"]
        review = action["metadata"]["anna_warning_review"]
        self.assertEqual(review["source"], "anna-app-scoped-one-time-warning-review")
        self.assertEqual(review["reviewed_rule_ids"], ["ai_risk_flag"])
        self.assertRegex(review["approval_nonce_sha256"], r"^[0-9a-f]{64}$")
        matched = data["decision_receipt"]["payload"]["decision"]["matched_rules"]
        self.assertTrue(any(
            item["rule"] == "ai_risk_flag" and item["severity"] == "WARN"
            for item in matched
        ))
        verified = plugin._verigate_verify_execution_authorization({
            "authorization_json": json.dumps(authorization)
        })
        self.assertTrue(verified["data"]["verified"], verified)

    def test_warn_without_separate_warning_review_still_has_no_execution_authority(self):
        result = self._authorize(
            ai_flags_json=json.dumps([
                {"code": "urgency_pressure", "message": "Needs manual review"}
            ])
        )
        self.assertTrue(result["success"], result)
        self.assertEqual(
            result["data"]["decision_receipt"]["payload"]["decision"]["decision"],
            "WARN",
        )
        self.assertIsNone(result["data"]["execution_authorization"])

    def test_warning_review_cannot_override_daily_spend_cap(self):
        engine, private_key = plugin._get_state()
        agent_id = plugin._anna_installation_principal(private_key)
        for amount in (10.0, 495.0, 495.0, 495.0, 495.0):
            intent = PaymentIntent(
                agent_id=agent_id,
                payee=VALID_PAYEE,
                asset="USDC",
                network="base",
                amount=amount,
            )
            decision = engine.evaluate(intent)

        # evaluate() persists each decision once as part of the same policy
        # transaction; the setup must reach exactly 1,990 USDC.
        self.assertEqual(engine.storage.spent_today(agent_id, "USDC"), 1990.0)

        # Prior spend is 1,990 USDC; even an explicit WARN review cannot
        # authorize another 20 USDC because the rolling daily cap is a hard BLOCK.
        result, _ = self._authorize_warning_review(
            amount=20,
            ai_flags_json=json.dumps([
                {"code": "urgency_pressure", "message": "Manual review requested"}
            ]),
            agent_id=agent_id,
        )
        self.assertFalse(result["success"])
        self.assertIn("fresh policy decision is BLOCK", result["error"])

    def test_warning_review_cannot_override_block(self):
        result, _ = self._authorize_warning_review(amount=600)
        self.assertFalse(result["success"])
        self.assertIn("fresh policy decision is BLOCK", result["error"])

    def test_warning_review_must_match_fresh_warning_rule_ids(self):
        result, _ = self._authorize_warning_review(
            amount=25,
            reviewed_rule_ids=["confirmation_required"],
        )
        self.assertFalse(result["success"])
        self.assertIn("reviewed warning rules do not match", result["error"])

    def test_warning_review_does_not_bypass_dynamic_authority_limit(self):
        result, _ = self._authorize_warning_review(
            amount=50.01,
            reviewed_rule_ids=["ai_risk_flag", "new_payee_cap_exceeded"],
        )
        self.assertFalse(result["success"])
        self.assertIn("action exceeds dynamic authority limit", result["error"])

    def test_warning_review_app_approval_is_consumed_once(self):
        result, args = self._authorize_warning_review(amount=25)
        self.assertTrue(result["success"], result)
        replay = asyncio.run(plugin._verigate_authorize_payment(args))
        self.assertFalse(replay["success"])
        self.assertIn("no app-scoped UI approval", replay["error"])

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
