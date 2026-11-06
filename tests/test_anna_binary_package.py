import json
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from anna.package_binary import build_package_manifest, verify_archive


TOOL_ID = "tool-rinat-verigate-authority-2um8gwhw"
DESCRIPTION = "Checks policy only. Does not execute transactions."


class AnnaBinaryPackageTest(unittest.TestCase):
    def test_windows_distribution_manifest_has_exe_entrypoint(self):
        manifest = build_package_manifest(
            "0.1.4", DESCRIPTION, "verigate-authority.exe", windows=True
        )
        self.assertEqual(manifest["name"], TOOL_ID)
        self.assertEqual(manifest["version"], "0.1.4")
        self.assertEqual(
            manifest["runtime"]["binary"]["entrypoint"]["default"],
            "verigate-authority.exe",
        )
        self.assertNotIn("permissions", manifest["runtime"]["binary"])

    def test_unix_distribution_manifest_declares_executable_permission(self):
        manifest = build_package_manifest(
            "0.1.4", DESCRIPTION, "verigate-authority", windows=False
        )
        self.assertEqual(
            manifest["runtime"]["binary"]["entrypoint"]["default"],
            "verigate-authority",
        )
        self.assertEqual(
            manifest["runtime"]["binary"]["permissions"],
            {"verigate-authority": "0o755"},
        )

    def test_verify_accepts_windows_binary_and_manifest(self):
        manifest = build_package_manifest(
            "0.1.4", DESCRIPTION, "verigate-authority.exe", windows=True
        )
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "valid.zip"
            with zipfile.ZipFile(archive, "w") as packaged:
                packaged.writestr("verigate-authority.exe", b"test-binary")
                packaged.writestr("manifest.json", json.dumps(manifest))
            verify_archive(archive, "verigate-authority.exe", windows=True)

    def test_verify_accepts_unix_binary_and_manifest(self):
        manifest = build_package_manifest(
            "0.1.4", DESCRIPTION, "verigate-authority", windows=False
        )
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "valid.tar.gz"
            with tarfile.open(archive, "w:gz") as packaged:
                binary = tarfile.TarInfo("verigate-authority")
                binary.size = len(b"test-binary")
                import io
                packaged.addfile(binary, io.BytesIO(b"test-binary"))
                payload = json.dumps(manifest).encode("utf-8")
                info = tarfile.TarInfo("manifest.json")
                info.size = len(payload)
                packaged.addfile(info, io.BytesIO(payload))
            verify_archive(archive, "verigate-authority", windows=False)

    def test_verify_rejects_missing_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "missing-manifest.zip"
            with zipfile.ZipFile(archive, "w") as packaged:
                packaged.writestr("verigate-authority.exe", b"test-binary")
            with self.assertRaisesRegex(SystemExit, "invalid archive layout"):
                verify_archive(archive, "verigate-authority.exe", windows=True)

    def test_verify_rejects_wrong_entrypoint(self):
        manifest = build_package_manifest(
            "0.1.4", DESCRIPTION, "wrong.exe", windows=True
        )
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "wrong-entry.zip"
            with zipfile.ZipFile(archive, "w") as packaged:
                packaged.writestr("verigate-authority.exe", b"test-binary")
                packaged.writestr("manifest.json", json.dumps(manifest))
            with self.assertRaisesRegex(SystemExit, "entrypoint mismatch"):
                verify_archive(archive, "verigate-authority.exe", windows=True)


if __name__ == "__main__":
    unittest.main()
