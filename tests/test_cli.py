import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.proof_engine import canonical
from core.proof_package import build_proof_package, serialize_proof_package
from tests.test_reference_lifecycle import VerigateReferenceLifecycleTest


ROOT = Path(__file__).resolve().parents[1]


class PortableProofCliTests(unittest.TestCase):
    def test_genesis_demo_script_completes_end_to_end(self):
        script = ROOT / "examples" / "genesis_demo.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("GENESIS 2.0 DEMO: PASS", result.stdout)
        self.assertIn("RESULT: VALID", result.stdout)
        self.assertIn("RESULT: INVALID", result.stdout)

    def test_tamper_enforcement_demo_completes(self):
        script = ROOT / "demo_tamper_enforcement.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("VERIGATE: BLOCK"), 2)
        self.assertIn("Broadcasts: 0", result.stdout)
        self.assertIn("VERIGATE: ALLOW", result.stdout)
        self.assertIn("Broadcasts: 1", result.stdout)

    def test_authority_package_verifies_after_runtime_shutdown(self):
        lifecycle = VerigateReferenceLifecycleTest("test_reference_lifecycle_is_offline_verifiable")
        lifecycle.setUp()
        try:
            package = build_proof_package(lifecycle._valid_manifest())
            raw = serialize_proof_package(package)
            with tempfile.TemporaryDirectory() as tmp:
                proof_path = Path(tmp) / "authority-proof.json"
                proof_path.write_bytes(raw)
                lifecycle.storage.close()

                result = subprocess.run(
                    [sys.executable, "cli.py", "verify", str(proof_path), "--public-key", str(lifecycle.public_path), "--format", "text"],
                    cwd=Path(__file__).resolve().parents[1],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("RESULT: VALID", result.stdout)
                for label in (
                    "PACKAGE INTEGRITY",
                    "CRYPTOGRAPHIC MANIFEST",
                    "AUTHORITY PROTOCOL",
                    "AUTHORIZATION",
                    "EXECUTION",
                    "HISTORICAL AUTHORITY",
                    "LEARNING / POST-AUTHORITY",
                ):
                    self.assertIn(label, result.stdout)

                document = json.loads(proof_path.read_text(encoding="utf-8"))
                document["package"]["agent_id"] = "tampered-agent"
                proof_path.write_text(json.dumps(document), encoding="utf-8")
                tampered = subprocess.run(
                    [sys.executable, "cli.py", "verify", str(proof_path), "--public-key", str(lifecycle.public_path), "--format", "text"],
                    cwd=Path(__file__).resolve().parents[1],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(tampered.returncode, 0)
                self.assertIn("RESULT: INVALID", tampered.stdout)
        finally:
            try:
                lifecycle.storage.close()
            except Exception:
                pass
            lifecycle.tmp.cleanup()


if __name__ == "__main__":
    unittest.main()

