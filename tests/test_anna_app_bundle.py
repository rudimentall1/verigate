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

    def test_manifest_declares_anna_llm_and_verigate_tool(self):
        host_api = self.manifest["ui"]["host_api"]
        self.assertIn("complete", host_api["llm"])
        self.assertIn("required:bundled:verigate-authority", host_api["tools"])

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
        self.assertIn('id="interpret-btn"', self.html)
        self.assertIn('id="check-btn"', self.html)
        self.assertIn("AnnaAppRuntime.connect()", self.js)
        self.assertIn("state.anna.llm.complete", self.js)
        self.assertIn('method: "verigate_check"', self.js)

    def test_decision_is_taken_from_verigate_receipt(self):
        self.assertIn("decision_receipt", self.js)
        self.assertIn('["ALLOW", "WARN", "BLOCK"]', self.js)
        self.assertIn("matched_rules", self.js)
        self.assertIn("Never change ALLOW, WARN, or BLOCK", self.js)

    def test_runtime_tool_id_sidecar_is_loaded(self):
        self.assertIn('src="anna-tool-ids.js"', self.html)
        self.assertIn("window.__ANNA_TOOL_IDS__", self.js)

    def test_listing_version_is_currently_aligned(self):
        self.assertEqual(self.app["slug"], "verigate-authority")
        self.assertGreaterEqual(tuple(map(int, self.app["version"].split("."))), (0, 1, 4))


if __name__ == "__main__":
    unittest.main()
