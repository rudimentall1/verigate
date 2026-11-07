"""Concurrent cold-start regression test for the Anna Executa process state."""
import importlib.util
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "anna" / "executas" / "verigate-authority" / "verigate_authority_plugin.py"


class AnnaStateInitializationTest(unittest.TestCase):
    def test_concurrent_first_invocations_create_one_state_and_one_issuer(self):
        spec = importlib.util.spec_from_file_location(
            "verigate_authority_state_lock_under_test", PLUGIN
        )
        plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin)
        fake_engine = object()
        fake_key = object()
        calls = []
        calls_lock = threading.Lock()

        def ensure_keypair(private_path, public_path):
            with calls_lock:
                calls.append((private_path, public_path))
            # Force concurrent callers to overlap the lazy initialization window.
            time.sleep(0.05)
            return fake_key

        with tempfile.TemporaryDirectory(prefix="verigate-state-lock-") as tmp:
            plugin._state = None
            with patch.dict(
                __import__("os").environ,
                {"VERIGATE_ANNA_DATA_DIR": str(Path(tmp) / "state")},
            ):
                with patch("attest.keys.ensure_keypair", side_effect=ensure_keypair), patch(
                    "core.engine.GuardrailEngine", return_value=fake_engine
                ), patch("core.storage.Storage", return_value=object()):
                    with ThreadPoolExecutor(max_workers=12) as pool:
                        states = list(pool.map(lambda _: plugin._get_state(), range(48)))

            self.assertEqual(len(calls), 1)
            self.assertTrue(all(state is states[0] for state in states))
            self.assertIs(states[0][0], fake_engine)
            self.assertIs(states[0][1], fake_key)
            self.assertEqual((Path(tmp) / "state" / "issuer.key").name, "issuer.key")
        plugin._state = None


if __name__ == "__main__":
    unittest.main()
