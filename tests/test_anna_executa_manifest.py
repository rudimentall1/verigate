"""The Anna Executa `describe` manifest must match protocol 1.1.

Anna rejected v0.1.1 with "describe handshake failed" because `parameters` was a
JSON Schema object instead of a list and the manifest had no `description`.
"""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "anna" / "executas" / "verigate-authority" / "verigate_authority_plugin.py"
SMOKE = Path(__file__).resolve().parents[1] / "anna" / "smoke_binary.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExecutaManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plugin = _load(PLUGIN, "verigate_authority_plugin_under_test")
        cls.smoke = _load(SMOKE, "anna_smoke_under_test")

    def test_manifest_passes_protocol_check(self):
        self.smoke.check_manifest(self.plugin.MANIFEST)

    def test_parameters_is_a_list_and_description_present(self):
        manifest = self.plugin.MANIFEST
        self.assertTrue(manifest["description"])
        self.assertIsInstance(manifest["tools"][0]["parameters"], list)

    def test_schema_style_parameters_are_rejected_by_check(self):
        broken = json.loads(json.dumps(self.plugin.MANIFEST))
        broken["tools"][0]["parameters"] = {"type": "object", "properties": {}}
        with self.assertRaises(SystemExit):
            self.smoke.check_manifest(broken)

    def test_version_matches_executa_json(self):
        executa = json.loads((PLUGIN.parent / "executa.json").read_text(encoding="utf-8"))
        self.assertEqual(self.plugin.MANIFEST["version"], executa["version"])

    def test_describe_does_not_touch_filesystem_or_engine(self):
        self.assertIsNone(self.plugin._state)
        self.plugin.handle({"method": "describe"})
        self.assertIsNone(self.plugin._state)

    def test_protocol_errors(self):
        with self.assertRaises(self.plugin.RpcError) as ctx:
            self.plugin.handle({"method": "invoke", "params": {"tool": "nope", "arguments": {}}})
        self.assertEqual(ctx.exception.code, -32601)
        with self.assertRaises(self.plugin.RpcError) as ctx:
            self.plugin.handle({"method": "invoke", "params": {"tool": "verigate_check", "arguments": {}}})
        self.assertEqual(ctx.exception.code, -32602)

    def test_plugin_process_answers_describe_and_survives_bad_input(self):
        proc = subprocess.run(
            [sys.executable, str(PLUGIN)],
            input='{"jsonrpc":"2.0","id":1,"method":"describe"}\nnot json\n{"jsonrpc":"2.0","id":2,"method":"health"}\n',
            text=True, capture_output=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        frames = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(frames), 3)
        self.assertIn("result", frames[0])
        self.assertEqual(frames[1]["error"]["code"], -32700)
        self.assertEqual(frames[2]["result"]["status"], "ready")


if __name__ == "__main__":
    unittest.main()