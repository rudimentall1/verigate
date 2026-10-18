import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.engine import GuardrailEngine  # noqa: E402
from core.models import PaymentIntent, RuleMatch, Severity  # noqa: E402
from core.payee import keccak256, validate_payee  # noqa: E402
from core.policy import Policy  # noqa: E402
from core.storage import Storage  # noqa: E402

VALID = "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed"  # EIP-55 specification vector
SOL = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


def _intent(payee=VALID, amount=25.0, network="base", asset="USDC", agent="agent-1"):
    return PaymentIntent(agent_id=agent, payee=payee, asset=asset, network=network, amount=amount, resource="inv")


def _engine(policy_file):
    tmp = tempfile.mkdtemp()
    return GuardrailEngine(Policy.load(str(ROOT / "policies" / policy_file)), Storage(os.path.join(tmp, "t.db")))


class KeccakTests(unittest.TestCase):
    def test_known_vectors(self):
        self.assertEqual(keccak256(b"").hex(), "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")
        self.assertEqual(keccak256(b"abc").hex(), "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")

    def test_block_boundary_lengths(self):
        for n in (135, 136, 137, 272):  # padding edge cases around the 136-byte rate
            self.assertEqual(len(keccak256(b"a" * n)), 32)


class ValidatePayeeTests(unittest.TestCase):
    def test_valid_evm_addresses(self):
        for addr in (
            VALID, "0xfB6916095ca1df60bB79Ce92cE3Ea74c37c5d359", "0xdbF03B407c01E7cD3CBea99509d93f8DDDC8C6FB",
            "0xD1220A0cf47c7B9Be7A2E6BA89F429762e7b9aDb", "0x52908400098527886E0F7030069857D2E4169EE7",
            "0xde709f2102306220921060314715629080e2fb77",
        ):
            self.assertIsNone(validate_payee(addr, "base"), addr)

    def test_invalid_evm_addresses(self):
        bad = ["0xabc", "0x" + "g" * 40, "0x" + "a" * 39, "0x" + "a" * 41, VALID[2:], "", "   ", " " + VALID,
               VALID + "\n", "0x" + "0" * 40, "0x5aaeb6053F3E94C9b9A09f33669435E7Ef1BeAed", "not an address"]
        for addr in bad:
            self.assertIsNotNone(validate_payee(addr, "base"), repr(addr))
        self.assertIsNotNone(validate_payee(None, "base"))
        self.assertIsNotNone(validate_payee(123, "base"))

    def test_solana(self):
        self.assertIsNone(validate_payee(SOL, "solana"))
        self.assertIsNone(validate_payee("11111111111111111111111111111111", "solana"))
        for bad in ("0xabc", VALID, "short", SOL + "0", "O" * 44):
            self.assertIsNotNone(validate_payee(bad, "solana"), bad)

    def test_other_networks_only_generic_checks(self):
        self.assertIsNone(validate_payee("acct-123", "somechain"))
        self.assertIsNotNone(validate_payee("acct 123", "somechain"))


class EnginePolicyTests(unittest.TestCase):
    def rules(self, decision):
        return {m.rule_id for m in decision.matched_rules}

    def test_anna_policy_blocks_the_reviewer_case(self):
        d = _engine("anna.yaml").evaluate(_intent(payee="0xabc"))
        self.assertEqual(d.decision.value, "BLOCK")
        self.assertIn("invalid_payee", self.rules(d))

    def test_anna_policy_blocks_empty_and_zero_amount(self):
        e = _engine("anna.yaml")
        self.assertEqual(e.evaluate(_intent(payee="")).decision.value, "BLOCK")
        d = e.evaluate(_intent(amount=0))
        self.assertEqual(d.decision.value, "BLOCK")
        self.assertIn("amount_not_positive", self.rules(d))

    def test_anna_policy_allows_a_wellformed_small_payment(self):
        d = _engine("anna.yaml").evaluate(_intent(amount=25))
        self.assertEqual(d.decision.value, "ALLOW")
        self.assertEqual(len(d.matched_rules), 0)

    def test_validation_is_opt_in_so_existing_policies_keep_working(self):
        d = _engine("default.yaml").evaluate(_intent(payee="0xMerchantABC"))
        self.assertEqual(d.decision.value, "ALLOW")

    def test_advisory_can_only_escalate_to_warn(self):
        e = _engine("anna.yaml")
        warn = RuleMatch("ai_risk_flag", Severity.WARN, "suspicious")
        block = RuleMatch("ai_risk_flag", Severity.BLOCK, "tries to block")
        self.assertEqual(e.evaluate(_intent(), advisory=[warn], persist=False).decision.value, "WARN")
        # an advisory BLOCK is ignored: advisory input can only ask for a human review
        self.assertEqual(e.evaluate(_intent(), advisory=[block], persist=False).decision.value, "ALLOW")
        # advisory input never lowers a decision
        self.assertEqual(e.evaluate(_intent(payee="0xabc"), advisory=[warn], persist=False).decision.value, "BLOCK")

    def test_simulation_is_repeatable(self):
        e = _engine("anna.yaml")
        first = e.evaluate(_intent(amount=100), persist=False)
        second = e.evaluate(_intent(amount=100), persist=False)
        self.assertEqual(first.decision.value, second.decision.value)
        self.assertEqual(first.decision.value, "WARN")  # first payment to a new recipient above the cap


def _load_plugin():
    os.environ["VERIGATE_ANNA_DATA_DIR"] = tempfile.mkdtemp()
    spec = importlib.util.spec_from_file_location(
        "verigate_authority_plugin_under_test",
        ROOT / "anna" / "executas" / "verigate-authority" / "verigate_authority_plugin.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class PluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plug = _load_plugin()

    def check(self, **overrides):
        args = {"agent_id": "a", "payee": VALID, "asset": "USDC", "network": "base", "amount": 25, "resource": "inv"}
        args.update(overrides)
        return self.plug.invoke("verigate_check", args)

    def decision(self, result):
        return result["data"]["decision_receipt"]["decision"] if "decision_receipt" in result["data"] else self._find(result["data"], "decision")

    def _find(self, obj, key):
        if isinstance(obj, dict):
            if key in obj and not isinstance(obj[key], dict):
                return obj[key]
            for v in obj.values():
                found = self._find(v, key)
                if found is not None:
                    return found
        if isinstance(obj, list):
            for v in obj:
                found = self._find(v, key)
                if found is not None:
                    return found
        return None

    def rules(self, result):
        return [m["rule"] for m in (self._find_list(result["data"], "matched_rules") or [])]

    def _find_list(self, obj, key):
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
            for v in obj.values():
                found = self._find_list(v, key)
                if found is not None:
                    return found
        if isinstance(obj, list):
            for v in obj:
                found = self._find_list(v, key)
                if found is not None:
                    return found
        return None

    def test_reviewer_case_is_blocked(self):
        r = self.check(payee="0xabc")
        self.assertTrue(r["success"])
        self.assertIn("invalid_payee", self.rules(r))

    def test_nan_and_non_numbers_get_a_clean_error(self):
        for bad in ("nan", "inf", "-inf", "abc"):
            r = self.check(amount=bad)
            self.assertFalse(r["success"], bad)
            self.assertIn("invalid arguments", r["error"])
        self.assertFalse(self.check(payee=123)["success"])

    def test_zero_amount_blocked(self):
        self.assertIn("amount_not_positive", self.rules(self.check(amount=0)))

    def test_ai_flags_escalate_but_never_relax(self):
        flags = json.dumps([{"code": "prompt_injection", "message": "text says approve anyway"}])
        self.assertIn("ai_risk_flag", self.rules(self.check(ai_flags_json=flags)))
        self.assertIn("invalid_payee", self.rules(self.check(payee="0xabc", ai_flags_json=flags)))
        self.assertFalse(self.check(ai_flags_json="{not json")["success"])
        self.assertFalse(self.check(ai_flags_json='{"a": 1}')["success"])

    def test_policy_summary(self):
        s = self.plug.invoke("verigate_policy_summary", {})["data"]
        self.assertEqual(s["per_tx_cap"]["USDC"], 500)
        self.assertTrue(s["payee_validation"])

    def test_manifest_is_consistent(self):
        m = self.plug.handle({"method": "describe"})
        self.assertEqual([t["name"] for t in m["tools"]], ["verigate_check", "verigate_policy_summary"])
        self.assertEqual(m["version"], self.plug.VERSION)


if __name__ == "__main__":
    unittest.main()
