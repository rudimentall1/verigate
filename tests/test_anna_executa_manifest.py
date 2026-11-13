"""The Anna Executa must expose a valid describe manifest and negotiate protocol 2.0 for APS.

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

    def test_published_protocol_manifest_matches_runtime_describe(self):
        protocol_manifest = json.loads((PLUGIN.parent / "manifest.json").read_text(encoding="utf-8"))
        def differences(left, right, path="$"):
            if isinstance(left, dict) and isinstance(right, dict):
                result = []
                for key in sorted(set(left) | set(right)):
                    if key not in left:
                        result.append(f"{path}.{key}: missing from published manifest")
                    elif key not in right:
                        result.append(f"{path}.{key}: missing from runtime manifest")
                    else:
                        result.extend(differences(left[key], right[key], f"{path}.{key}"))
                return result
            if isinstance(left, list) and isinstance(right, list):
                result = []
                if len(left) != len(right):
                    result.append(f"{path}: list length {len(left)} != {len(right)}")
                for index, (a, b) in enumerate(zip(left, right)):
                    result.extend(differences(a, b, f"{path}[{index}]"))
                return result
            return [] if left == right else [f"{path}: published={left!r}; runtime={right!r}"]

        self.assertEqual(differences(protocol_manifest, self.plugin.MANIFEST), [])

    def test_manifest_passes_protocol_check(self):
        self.smoke.check_manifest(self.plugin.MANIFEST)

    def test_sampling_tool_is_rejected_without_llm_sample_capability(self):
        manifest = json.loads(json.dumps(self.plugin.MANIFEST))
        manifest.pop("host_capabilities", None)
        with self.assertRaises(SystemExit):
            self.smoke.check_manifest(manifest)

    def test_parameters_is_a_list_and_description_present(self):
        manifest = self.plugin.MANIFEST
        self.assertTrue(manifest["description"])
        self.assertIsInstance(manifest["tools"][0]["parameters"], list)

    def test_schema_style_parameters_are_rejected_by_check(self):
        broken = json.loads(json.dumps(self.plugin.MANIFEST))
        broken["tools"][0]["parameters"] = {"type": "object", "properties": {}}
        with self.assertRaises(SystemExit):
            self.smoke.check_manifest(broken)

    def test_policy_summary_parameters_match_runtime_arguments(self):
        tool = next(t for t in self.plugin.MANIFEST["tools"] if t["name"] == "verigate_policy_summary")
        self.assertEqual([p["name"] for p in tool["parameters"]], ["agent_id", "payee", "asset"])
        self.assertTrue(all(p["required"] is False for p in tool["parameters"]))

    def test_sampling_host_capability_is_declared_and_nonce_approval_is_required(self):
        manifest = self.plugin.MANIFEST
        self.assertIn("llm.sample", manifest["host_capabilities"])
        tool = next(t for t in manifest["tools"] if t["name"] == "verigate_authorize_payment")
        params = {p["name"]: p for p in tool["parameters"]}
        self.assertTrue(params["confirmation_nonce"]["required"])
        self.assertNotIn("human_confirmed", params)
        consume = next(t for t in manifest["tools"] if t["name"] == "verigate_consume_execution_authorization")
        consume_params = {p["name"]: p for p in consume["parameters"]}
        self.assertTrue(consume_params["confirmation_nonce"]["required"])
        submitted = next(t for t in manifest["tools"] if t["name"] == "verigate_record_wallet_submission_receipt")
        submitted_params = {p["name"]: p for p in submitted["parameters"]}
        self.assertTrue(all(submitted_params[name]["required"] for name in (
            "authorization_id", "transaction_hash", "sender", "confirmation_nonce"
        )))
        self.assertIn("self-report", submitted["description"])
        outcome = next(t for t in manifest["tools"] if t["name"] == "verigate_record_wallet_outcome_receipt")
        outcome_params = {p["name"]: p for p in outcome["parameters"]}
        self.assertTrue(all(outcome_params[name]["required"] for name in (
            "authorization_id", "outcome", "phase", "error_message", "confirmation_nonce"
        )))
        self.assertIn("EIP-1193 error 4001", outcome["description"])

    def test_initialize_negotiates_v2_sampling_and_storage(self):
        result = self.plugin.handle({"method": "initialize", "params": {"protocolVersion": "2.0"}})
        self.assertEqual(result["protocolVersion"], "2.0")
        self.assertIn("sampling", result["client_capabilities"])
        self.assertIn("storage", result["client_capabilities"])
        self.assertIn("llm.sample", self.plugin.MANIFEST["host_capabilities"])
        self.assertNotIn("storage", result["capabilities"])

    def test_protocol_v1_disables_sampling_and_storage(self):
        previous_sampling = self.plugin._sampling._sampling_disabled_reason
        previous_storage = self.plugin._storage._disabled_reason
        try:
            result = self.plugin.handle({"method": "initialize", "params": {"protocolVersion": "1.1"}})
            self.assertEqual(result["protocolVersion"], "1.1")
            self.assertEqual(result["client_capabilities"], {})
            self.assertIn("did not negotiate", self.plugin._sampling._sampling_disabled_reason)
            self.assertIn("did not negotiate", self.plugin._storage._disabled_reason)
        finally:
            self.plugin._sampling._sampling_disabled_reason = previous_sampling
            self.plugin._storage._disabled_reason = previous_storage

    def test_sync_tool_dispatch_cannot_issue_or_consume_execution_authority(self):
        for tool in (
            "verigate_authorize_payment",
            "verigate_consume_execution_authorization",
            "verigate_record_wallet_submission_receipt",
            "verigate_record_wallet_outcome_receipt",
        ):
            with self.subTest(tool=tool), self.assertRaises(self.plugin.RpcError):
                self.plugin.handle({"method": "invoke", "params": {
                    "tool": tool,
                    "arguments": {"human_confirmed": True},
                }})

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
            input='{"jsonrpc":"2.0","id":0,"method":"initialize"}\n{"jsonrpc":"2.0","id":1,"method":"describe"}\nnot json\n{"jsonrpc":"2.0","id":2,"method":"health"}\n',
            text=True, capture_output=True, timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        frames = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
        self.assertEqual(len(frames), 4)
        self.assertEqual(frames[0]["result"]["protocolVersion"], "2.0")
        self.assertIn("sampling", frames[0]["result"]["client_capabilities"])
        self.assertIn("storage", frames[0]["result"]["client_capabilities"])
        self.assertIn("result", frames[1])
        self.assertEqual(frames[2]["error"]["code"], -32700)
        self.assertEqual(frames[3]["result"]["status"], "ready")


if __name__ == "__main__":
    unittest.main()