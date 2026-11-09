import json
import os
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from anna.package_binary import (
    build_package_manifest,
    verify_archive,
    write_reproducible_archive,
)
from anna.verify_reproducible_binary import verify_reproducible_binary


TOOL_ID = "tool-verigate-authority-verigate-authority-28x5jku8"
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
                binary.mode = 0o755
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

    def test_windows_archive_is_reproducible_and_metadata_is_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "verigate-authority.exe"
            binary.write_bytes(b"same frozen executable bytes")
            manifest = (
                json.dumps(build_package_manifest(
                    "0.1.15", DESCRIPTION, binary.name, windows=True
                ), indent=2) + "\n"
            ).encode("utf-8")
            first = root / "first.zip"
            second = root / "second.zip"

            write_reproducible_archive(
                first, binary, manifest, binary.name, windows=True, epoch=1_700_000_000
            )
            os.utime(binary, (1_800_000_000, 1_800_000_000))
            write_reproducible_archive(
                second, binary, manifest, binary.name, windows=True, epoch=1_700_000_000
            )

            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as packaged:
                self.assertEqual(packaged.namelist(), [binary.name, "manifest.json"])
                for item in packaged.infolist():
                    self.assertEqual(item.date_time, (2023, 11, 14, 22, 13, 20))
                    self.assertEqual(item.create_system, 3)
                    self.assertEqual(item.extra, b"")
                self.assertEqual(packaged.read(binary.name), b"same frozen executable bytes")

    def test_unix_archive_is_reproducible_and_metadata_is_normalized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "verigate-authority"
            binary.write_bytes(b"same frozen executable bytes")
            manifest = (
                json.dumps(build_package_manifest(
                    "0.1.15", DESCRIPTION, binary.name, windows=False
                ), indent=2) + "\n"
            ).encode("utf-8")
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"

            write_reproducible_archive(
                first, binary, manifest, binary.name, windows=False, epoch=1_700_000_000
            )
            os.utime(binary, (1_800_000_000, 1_800_000_000))
            write_reproducible_archive(
                second, binary, manifest, binary.name, windows=False, epoch=1_700_000_000
            )

            self.assertEqual(first.read_bytes(), second.read_bytes())
            with tarfile.open(first, "r:gz") as packaged:
                members = packaged.getmembers()
                self.assertEqual([item.name for item in members], [binary.name, "manifest.json"])
                for item in members:
                    self.assertEqual(item.mtime, 1_700_000_000)
                    self.assertEqual(item.uid, 0)
                    self.assertEqual(item.gid, 0)
                    self.assertEqual(item.uname, "")
                    self.assertEqual(item.gname, "")
                self.assertEqual(members[0].mode, 0o755)
                self.assertEqual(members[1].mode, 0o644)
                self.assertEqual(packaged.extractfile(binary.name).read(), b"same frozen executable bytes")

    def test_reproducibility_gate_rejects_missing_fixed_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "app.exe"
            binary.write_bytes(b"binary")
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(SystemExit, "PYTHONHASHSEED"):
                    verify_reproducible_binary(binary)

    def test_reproducibility_gate_builds_twice_and_accepts_matching_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "app.exe"
            binary.write_bytes(b"first build")
            def build(*args, **kwargs):
                binary.write_bytes(b"same build")
            env = {"PYTHONHASHSEED": "0", "SOURCE_DATE_EPOCH": "1700000000"}
            with patch.dict(os.environ, env, clear=True), patch(
                "anna.verify_reproducible_binary.subprocess.run", side_effect=build
            ) as runner:
                first, second = verify_reproducible_binary(binary)
            self.assertEqual(first, second)
            self.assertEqual(runner.call_count, 2)

    def test_reproducibility_gate_fails_on_different_binary_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "app.exe"
            binary.write_bytes(b"initial")
            calls = 0
            def build(*args, **kwargs):
                nonlocal calls
                calls += 1
                binary.write_bytes(b"build one" if calls == 1 else b"build two")
            env = {"PYTHONHASHSEED": "0", "SOURCE_DATE_EPOCH": "1700000000"}
            with patch.dict(os.environ, env, clear=True), patch(
                "anna.verify_reproducible_binary.subprocess.run", side_effect=build
            ):
                with self.assertRaisesRegex(SystemExit, "REPRODUCIBILITY FAILURE"):
                    verify_reproducible_binary(binary)


if __name__ == "__main__":
    unittest.main()
