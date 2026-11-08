"""Fail-closed tests for Anna Executa's persistent data-directory resolver."""
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PLUGIN = (
    Path(__file__).resolve().parents[1]
    / "anna" / "executas" / "verigate-authority"
    / "verigate_authority_plugin.py"
)


def _load_plugin():
    spec = importlib.util.spec_from_file_location(
        "verigate_authority_data_dir_under_test", PLUGIN
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AnnaDataDirectoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plugin = _load_plugin()

    def test_explicit_directory_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "persistent-state"
            with patch.dict(os.environ, {"VERIGATE_ANNA_DATA_DIR": str(target)}):
                self.assertEqual(self.plugin._resolve_data_dir(), target)
            self.assertTrue(target.is_dir())
            self.assertFalse((target / ".write-test").exists())

    def test_unwritable_explicit_directory_fails_without_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blocker = root / "not-a-directory"
            blocker.write_text("occupied", encoding="utf-8")
            fallback = root / "fallback"
            with patch.dict(
                os.environ,
                {"VERIGATE_ANNA_DATA_DIR": str(blocker / "state")},
            ):
                with patch.object(self.plugin, "_DEFAULT_DATA_DIR", fallback):
                    with self.assertRaisesRegex(
                        RuntimeError, "no writable Verigate data directory"
                    ):
                        self.plugin._resolve_data_dir()
            self.assertFalse(fallback.exists())

    def test_anna_workspace_is_used_for_cloud_durable_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "anna-workspace"
            with patch.dict(os.environ, {"ANNA_WORKSPACE_DIR": str(workspace)}, clear=True):
                self.assertEqual(
                    self.plugin._resolve_data_dir(),
                    workspace / "verigate-authority",
                )

    def test_unwritable_anna_workspace_fails_without_ephemeral_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blocker = root / "not-a-directory"
            blocker.write_text("occupied", encoding="utf-8")
            workspace = blocker / "workspace"
            fallback = root / "local-fallback"
            with patch.dict(os.environ, {"ANNA_WORKSPACE_DIR": str(workspace)}, clear=True):
                with patch.object(self.plugin, "_DEFAULT_DATA_DIR", fallback):
                    with self.assertRaisesRegex(
                        RuntimeError, "no writable Verigate data directory"
                    ):
                        self.plugin._resolve_data_dir()
            self.assertFalse(fallback.exists())

    def test_legacy_resolution_still_uses_default_when_no_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "default-state"
            with patch.dict(os.environ, {}, clear=True):
                with patch.object(self.plugin, "_DEFAULT_DATA_DIR", target):
                    self.assertEqual(self.plugin._resolve_data_dir(), target)


if __name__ == "__main__":
    unittest.main()
