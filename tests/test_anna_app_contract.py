"""Cross-check the Anna App, bundled Executa, UI and release configuration."""
import importlib.util
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANNA = ROOT / "anna"
APP = json.loads((ANNA / "app.json").read_text(encoding="utf-8"))
APP_MANIFEST = json.loads((ANNA / "manifest.json").read_text(encoding="utf-8"))
EXECUTA = json.loads((ANNA / "executas" / "verigate-authority" / "executa.json").read_text(encoding="utf-8"))
PLUGIN_PATH = ANNA / "executas" / "verigate-authority" / "verigate_authority_plugin.py"
PLUGIN_SPEC = importlib.util.spec_from_file_location("anna_contract_plugin", PLUGIN_PATH)
PLUGIN = importlib.util.module_from_spec(PLUGIN_SPEC)
PLUGIN_SPEC.loader.exec_module(PLUGIN)


class AnnaAppContractTest(unittest.TestCase):
    def test_bundled_executa_path_and_handle_resolve(self):
        bundled = APP.get("bundled_executas", {})
        self.assertIn("verigate-authority", bundled)
        self.assertEqual(
            (ANNA / bundled["verigate-authority"]["path"]).resolve(),
            (ANNA / "executas" / "verigate-authority").resolve(),
        )
        self.assertTrue((ANNA / bundled["verigate-authority"]["path"] / "executa.json").is_file())

    def test_app_manifest_declares_the_bundled_executa_and_ui_entry(self):
        required = {item.get("tool_id") for item in APP_MANIFEST.get("required_executas", [])}
        self.assertIn("bundled:verigate-authority", required)
        allowed = APP_MANIFEST.get("ui", {}).get("host_api", {}).get("tools", [])
        self.assertIn("required:bundled:verigate-authority", allowed)
        entry = APP_MANIFEST.get("ui", {}).get("bundle", {}).get("entry")
        self.assertTrue(entry)
        self.assertTrue((ANNA / "bundle" / entry).is_file())

    def test_every_frontend_executa_method_exists_in_describe(self):
        source = (ANNA / "bundle" / "app.js").read_text(encoding="utf-8")
        invoked = set(re.findall(r'method:\s*["\'](verigate_[a-z0-9_]+)["\']', source))
        described = {tool["name"] for tool in PLUGIN.MANIFEST.get("tools", [])}
        self.assertTrue(invoked, "frontend must invoke at least one Verigate tool")
        self.assertEqual(invoked - described, set(), "frontend invokes methods absent from Executa describe")

    def test_tool_identity_and_version_are_consistent(self):
        self.assertEqual(EXECUTA["slug"], "verigate-authority")
        self.assertEqual(EXECUTA["tool_id"], "tool-dev-verigate-authority")
        self.assertEqual(EXECUTA["version"], PLUGIN.VERSION)
        self.assertEqual(EXECUTA["version"], PLUGIN.MANIFEST["version"])

    def test_binary_distribution_has_cloud_agent_linux_target(self):
        distribution = EXECUTA.get("distribution", {})
        self.assertEqual(distribution.get("active"), "binary")
        profile = distribution.get("profiles", {}).get("binary", {})
        self.assertEqual(profile.get("type"), "binary")
        artifacts = profile.get("binary_artifacts", {})
        self.assertIn("linux-x86_64", artifacts)
        for platform, artifact in artifacts.items():
            with self.subTest(platform=platform):
                self.assertTrue(artifact.get("path"))
                self.assertTrue(artifact.get("entrypoint"))
                self.assertIn(artifact.get("format"), {"tar.gz", "zip"})


if __name__ == "__main__":
    unittest.main()
