import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANNA = ROOT / "anna"


class AnnaAppBundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ANNA / "manifest.json").read_text(encoding="utf-8"))
        cls.app = json.loads((ANNA / "app.json").read_text(encoding="utf-8"))
        cls.html = (ANNA / "bundle" / "index.html").read_text(encoding="utf-8")
        cls.js = (ANNA / "bundle" / "app.js").read_text(encoding="utf-8")

    def test_manifest_uses_current_schema4_and_bundled_tool_allowlist(self):
        self.assertEqual(self.manifest.get("schema"), 4)
        self.assertNotIn("host_capabilities", self.manifest)
        self.assertNotIn("host_api", self.manifest["ui"])
        required = {item.get("tool_id") for item in self.manifest.get("required_executas", [])}
        self.assertIn("bundled:verigate-authority", required)

    def test_app_has_editable_user_action_fields(self):
        for element_id in (
            "action-description",
            "agent-id",
            "target",
            "asset",
            "network",
            "amount",
            "resource",
        ):
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', self.html)

    def test_ui_exposes_ai_interpretation_and_authority_check(self):
        self.assertIn('id="confirm-details"', self.html)
        self.assertIn('id="clarify-list"', self.html)
        self.assertIn('id="check-btn"', self.html)
        self.assertIn("AnnaAppRuntime.connect()", self.js)
        self.assertIn('method: "verigate_ai_review"', self.js)
        self.assertIn("sampling/createMessage", (ANNA / "executas" / "verigate-authority" / "verigate_authority_plugin.py").read_text(encoding="utf-8"))
        self.assertNotIn("state.anna.llm.complete", self.js)
        self.assertIn('method: "verigate_check"', self.js)
        self.assertIn('method: "verigate_policy_summary"', self.js)
        self.assertIn('method: "verigate_verify_decision_receipt"', self.js)
        self.assertIn("function extractReceiptVerification(response)", self.js)
        self.assertIn("current.content.find((item)", self.js)
        self.assertIn("JSON.parse(textBlock.text)", self.js)
        self.assertIn('["result", "data", "structuredContent", "output"]', self.js)
        self.assertIn('if (!data || data.verified !== true)', self.js)
        self.assertNotIn("outer?.success !== true || !data || data.verified !== true", self.js)
        self.assertIn('method: "verigate_consume_execution_authorization"', self.js)
        self.assertIn('method: "verigate_record_wallet_submission_receipt"', self.js)
        self.assertIn('wallet_submission_receipt', self.js)
        self.assertIn('id="wallet-execute-btn"', self.html)
        self.assertIn("eth_sendTransaction", self.js)
        self.assertIn("await verifyDecisionReceipt(envelope.receipt)", self.js)
        self.assertIn('id="issuer-public-key"', self.html)
        self.assertIn('id="ai-review-summary"', self.html)
        self.assertIn("Anna AI contextual risk review (advisory)", self.html)
        self.assertIn('review = await interpretRequest(description);', self.js)
        self.assertIn("perform a separate contextual risk review", self.js)
        self.assertIn("attempts to redirect funds to a different account or network", self.js)
        self.assertIn('if (state.busy) return;', self.js)
        self.assertIn('state.lastInterpretedDescription = description;', self.js)
        self.assertIn("function clearResult()", self.js)
        self.assertIn('input.addEventListener("input", () =>', self.js)
        self.assertIn('inputs.forEach((input) => { input.disabled = busy; })', self.js)
        self.assertIn("const requestId = ++state.requestId", self.js)
        self.assertIn("if (requestId !== state.requestId) return;", self.js)

    def test_decision_is_taken_from_verigate_receipt(self):
        self.assertIn("decision_receipt", self.js)
        self.assertIn('["ALLOW", "WARN", "BLOCK"]', self.js)
        self.assertIn("matched_rules", self.js)
        self.assertIn("never change ALLOW, WARN or BLOCK", self.js)

    def test_runtime_tool_id_sidecar_is_loaded(self):
        self.assertIn('src="anna-tool-ids.js"', self.html)
        self.assertIn("window.__ANNA_TOOL_IDS__", self.js)

    def test_listing_version_is_currently_aligned(self):
        self.assertEqual(self.app["slug"], "verigate-authority")
        self.assertGreaterEqual(tuple(map(int, self.app["version"].split("."))), (0, 1, 4))


if __name__ == "__main__":
    unittest.main()
