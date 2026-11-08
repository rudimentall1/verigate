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

    def test_app_manifest_schema4_declares_bundled_executa_and_ui_entry(self):
        self.assertEqual(APP_MANIFEST.get("schema"), 4)
        self.assertNotIn("host_capabilities", APP_MANIFEST)
        host_api = APP_MANIFEST.get("ui", {}).get("host_api", {})
        self.assertFalse(set(host_api) - {"credentials", "agent"})
        required = {item.get("tool_id") for item in APP_MANIFEST.get("required_executas", [])}
        self.assertIn("bundled:verigate-authority", required)
        entry = APP_MANIFEST.get("ui", {}).get("bundle", {}).get("entry")
        self.assertTrue(entry)
        self.assertTrue((ANNA / "bundle" / entry).is_file())

    def test_every_frontend_executa_method_exists_in_describe(self):
        source = (ANNA / "bundle" / "app.js").read_text(encoding="utf-8")
        invoked = set(re.findall(r'method:\s*["\'](verigate_[a-z0-9_]+)["\']', source))
        described = {tool["name"] for tool in PLUGIN.MANIFEST.get("tools", [])}
        self.assertTrue(invoked, "frontend must invoke at least one Verigate tool")
        self.assertEqual(invoked - described, set(), "frontend invokes methods absent from Executa describe")
        self.assertEqual(
            PLUGIN._REQUIRED_ARGS,
            ["agent_id", "payee", "asset", "network", "amount"],
            "payment check must derive required fields from verigate_check, not manifest position",
        )

    def test_cloud_workspace_is_authoritative_for_executa_state(self):
        source = PLUGIN_PATH.read_text(encoding="utf-8")
        self.assertIn('os.environ.get("ANNA_WORKSPACE_DIR")', source)
        self.assertIn('Path(workspace) / "verigate-authority"', source)
        self.assertIn("if authoritative:", source)
        self.assertIn("with _state_lock:", source)
        self.assertIn("if _state is None:", source)

    def test_app_scoped_confirmation_uses_schema4_and_v2_storage_handshake(self):
        self.assertNotIn("host_capabilities", APP_MANIFEST)
        # Executa's reverse Sampling capability must be declared here; the
        # declaration exposes the permission toggle, but does not grant it.
        self.assertIn("llm.sample", PLUGIN.MANIFEST["host_capabilities"])
        handshake = PLUGIN.handle({"method": "initialize", "params": {"protocolVersion": "2.0"}})
        self.assertIn("storage", handshake["client_capabilities"])
        self.assertIn("sampling", handshake["client_capabilities"])
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
        ci_workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        for command in ("smoke_binary.py", "package_binary.py"):
            version_lines = [line for line in ci_workflow.splitlines() if command in line]
            with self.subTest(command=command):
                self.assertTrue(version_lines, f"CI must declare a version for {command}")
                self.assertTrue(all(f'"{EXECUTA["version"]}"' in line for line in version_lines))
        self.assertRegex(workflow, r"publish_release:\s*[\s\S]*?default:\s*false[\s\S]*?type:\s*boolean")
        self.assertIn("push:\n    branches:\n      - integrate/anna-0.1.9-mainline", workflow)
        self.assertIn("github.event_name == 'workflow_dispatch' && inputs.publish_release", workflow)
        self.assertIn("EVENT_NAME: ${{ github.event_name }}", workflow)
        self.assertIn("--draft", workflow)
        self.assertIn("gh release upload", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        smoke = (ANNA / "smoke_binary.py").read_text(encoding="utf-8")
        self.assertIn('encoding="utf-8", errors="replace"', smoke)
        self.assertIn("queue.Queue", smoke)
        self.assertIn("describe-repeat", smoke)
        self.assertIn("describe-after-errors", smoke)
        build = (ANNA / "build_binary.py").read_text(encoding="utf-8")
        binary_name = re.search(r'"--name",\s*"([^"]+)"', build)
        self.assertIsNotNone(binary_name, "binary builder must name its output")
        for platform, artifact in EXECUTA["distribution"]["profiles"]["binary"]["binary_artifacts"].items():
            expected = binary_name.group(1) + (".exe" if platform == "windows-x86_64" else "")
            with self.subTest(platform=platform):
                self.assertEqual(artifact["entrypoint"], expected)

    def test_multiplatform_workflow_smokes_the_final_archives(self):
        workflow = (ROOT / ".github" / "workflows" / "anna-executa-binaries.yml").read_text(encoding="utf-8")
        package_step = workflow.index("      - name: Package binary")
        smoke_step = workflow.index("      - name: Smoke-test extracted release package")
        upload_step = workflow.index("      - name: Upload release package")
        self.assertLess(package_step, smoke_step)
        self.assertLess(smoke_step, upload_step)
        self.assertIn("python anna/smoke_package.py", workflow)
        verifier = (ANNA / "smoke_package.py").read_text(encoding="utf-8")
        self.assertIn("verify_checksum(archive_path)", verifier)
        self.assertIn("read_package(archive_path, target)", verifier)
        self.assertIn("smoke_binary.py", verifier)
        self.assertIn("verify_runner_target(target)", verifier)

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
