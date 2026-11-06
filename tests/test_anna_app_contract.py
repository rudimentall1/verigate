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
        required = next(item for item in APP_MANIFEST["required_executas"] if item.get("tool_id") == "bundled:verigate-authority")
        self.assertEqual(required.get("min_version"), EXECUTA["version"])

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

    def test_app_scoped_confirmation_storage_is_declared_end_to_end(self):
        expected = {"aps.scope.app.read", "aps.scope.app.write"}
        self.assertTrue(expected.issubset(set(APP_MANIFEST.get("host_capabilities", []))))
        self.assertTrue(expected.issubset(set(PLUGIN.MANIFEST.get("host_capabilities", []))))
        self.assertEqual(APP_MANIFEST.get("ui", {}).get("host_api", {}).get("storage"), ["set"])
        source = (ANNA / "bundle" / "app.js").read_text(encoding="utf-8")
        self.assertIn("state.anna.storage.set", source)
        self.assertIn("confirmation_nonce", source)
        self.assertNotIn("human_confirmed: true", source)

    def test_tool_identity_and_version_are_consistent(self):
        self.assertEqual(EXECUTA["slug"], "verigate-authority")
        self.assertEqual(EXECUTA["tool_id"], "tool-dev-verigate-authority")
        self.assertEqual(EXECUTA["version"], PLUGIN.VERSION)
        self.assertEqual(EXECUTA["version"], PLUGIN.MANIFEST["version"])

    def test_vendored_aps_sdk_is_included_in_python_and_binary_build(self):
        sdk = ANNA / "executas" / "verigate-authority" / "executa_sdk"
        self.assertTrue((sdk / "storage.py").is_file())
        self.assertTrue((sdk / "context.py").is_file())
        self.assertTrue((sdk / "LICENSE").is_file())
        pyproject = (sdk.parent / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('packages = ["executa_sdk"]', pyproject)
        build = (ANNA / "build_binary.py").read_text(encoding="utf-8")
        self.assertIn('"--collect-submodules", "executa_sdk"', build)

    def test_binary_workflow_default_tracks_executa_version_and_entrypoint(self):
        workflow = (ROOT / ".github" / "workflows" / "anna-executa-binaries.yml").read_text(encoding="utf-8")
        match = re.search(r'default:\s*["\']([^"\']+)["\']', workflow)
        self.assertIsNotNone(match, "binary workflow must declare a version default")
        self.assertEqual(match.group(1), EXECUTA["version"])
        self.assertRegex(workflow, r"publish_release:\s*[\s\S]*?default:\s*false[\s\S]*?type:\s*boolean")
        self.assertIn("if: ${{ inputs.publish_release }}", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        build = (ANNA / "build_binary.py").read_text(encoding="utf-8")
        binary_name = re.search(r'"--name",\s*"([^"]+)"', build)
        self.assertIsNotNone(binary_name, "binary builder must name its output")
        for platform, artifact in EXECUTA["distribution"]["profiles"]["binary"]["binary_artifacts"].items():
            expected = binary_name.group(1) + (".exe" if platform == "windows-x86_64" else "")
            with self.subTest(platform=platform):
                self.assertEqual(artifact["entrypoint"], expected)

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
