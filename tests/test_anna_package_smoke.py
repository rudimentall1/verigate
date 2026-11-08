"""Tests for the release-archive verifier used by every Anna target runner."""
import hashlib
import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "anna" / "smoke_package.py"
SPEC = importlib.util.spec_from_file_location("anna_smoke_package", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

TOOL_ID = "tool-rinat-verigate-authority-2um8gwhw"
MANIFEST = {
    "name": TOOL_ID,
    "display_name": "Verigate Authority",
    "version": "0.1.12",
    "description": "Test package",
    "runtime": {"binary": {"entrypoint": {"default": "verigate-authority"}}},
}


class AnnaPackageSmokeTests(unittest.TestCase):
    def test_unix_archive_manifest_entrypoint_and_executable_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "verigate-authority-0.1.12-linux-x86_64.tar.gz"
            with tarfile.open(archive, "w:gz") as package:
                binary = b"test-binary"
                info = tarfile.TarInfo("verigate-authority")
                info.size = len(binary)
                info.mode = 0o755
                package.addfile(info, io.BytesIO(binary))
                manifest = (json.dumps(MANIFEST) + "\n").encode("utf-8")
                info = tarfile.TarInfo("manifest.json")
                info.size = len(manifest)
                info.mode = 0o644
                package.addfile(info, io.BytesIO(manifest))

            parsed, entrypoint, payload = MODULE.read_package(archive, "linux-x86_64")
            self.assertEqual(parsed["name"], TOOL_ID)
            self.assertEqual(entrypoint, "verigate-authority")
            self.assertEqual(payload, b"test-binary")

    def test_windows_archive_manifest_and_executable_entrypoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "verigate-authority-0.1.12-windows-x86_64.zip"
            manifest = {
                **MANIFEST,
                "runtime": {"binary": {"entrypoint": {"default": "verigate-authority.exe"}}},
            }
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("verigate-authority.exe", b"test-binary")
                package.writestr("manifest.json", json.dumps(manifest))

            parsed, entrypoint, payload = MODULE.read_package(archive, "windows-x86_64")
            self.assertEqual(parsed["version"], "0.1.12")
            self.assertEqual(entrypoint, "verigate-authority.exe")
            self.assertEqual(payload, b"test-binary")

    def test_rejects_path_traversal_entrypoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bad.tar.gz"
            manifest = {
                **MANIFEST,
                "runtime": {"binary": {"entrypoint": {"default": "../verigate-authority"}}},
            }
            with tarfile.open(archive, "w:gz") as package:
                for name, payload, mode in (
                    ("../verigate-authority", b"bad", 0o755),
                    ("manifest.json", json.dumps(manifest).encode("utf-8"), 0o644),
                ):
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    info.mode = mode
                    package.addfile(info, io.BytesIO(payload))
            with self.assertRaises(SystemExit):
                MODULE.read_package(archive, "linux-x86_64")

    def test_sha256_checksum_matches_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "package.tar.gz"
            archive.write_bytes(b"package bytes")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            Path(str(archive) + ".sha256").write_text(
                f"{digest}  {archive.name}\n", encoding="utf-8"
            )
            self.assertEqual(MODULE.verify_checksum(archive), digest)
            archive.write_bytes(b"modified package")
            with self.assertRaises(SystemExit):
                MODULE.verify_checksum(archive)


if __name__ == "__main__":
    unittest.main()
