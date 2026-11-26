from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.storage import Storage

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "bootstrap_guardian_arc.py"
VALID_TARGET = "0x2222222222222222222222222222222222222222"


class GuardianArcBootstrapTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "verigate.db"
        self.key = self.root / "agent.pem"

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--db",
                str(self.db),
                "--private-key-path",
                str(self.key),
                *args,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_bootstrap_is_idempotent_and_creates_private_key_with_owner_only_mode(self):
        first = self.run_cli("--max-usdc", "5", "--allowed-target", VALID_TARGET)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(self.key.stat().st_mode & 0o777, 0o600)
        self.assertIn("VERIGATE_AGENT_ID=guardian-arc-agent", first.stdout)
        self.assertNotIn("PRIVATE KEY", first.stdout)

        second = self.run_cli("--max-usdc", "5", "--allowed-target", VALID_TARGET)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("VERIGATE_IDENTITY_ID=", second.stdout)

        storage = Storage(self.db)
        try:
            identity_id = next(
                line.split("=", 1)[1]
                for line in first.stdout.splitlines()
                if line.startswith("VERIGATE_IDENTITY_ID=")
            )
            self.assertTrue(storage.identity_is_active(identity_id))
            self.assertTrue(storage.capability_is_active("guardian-arc-usdc-mainnet"))
        finally:
            storage.close()

    def test_rejects_non_finite_capability_limits(self):
        for value in ("nan", "inf", "-inf"):
            with self.subTest(value=value):
                result = self.run_cli("--max-usdc", value)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("finite positive", result.stderr)

    def test_rejects_non_evm_allowed_target(self):
        result = self.run_cli("--allowed-target", "*")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("valid 20-byte EVM address", result.stderr)

    @unittest.skipUnless(os.name == "posix", "POSIX file mode checks only")
    def test_refuses_existing_private_key_with_group_or_other_permissions(self):
        private_key = Ed25519PrivateKey.generate()
        self.key.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        self.key.chmod(0o644)

        result = self.run_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("permissions", result.stderr)


if __name__ == "__main__":
    unittest.main()
