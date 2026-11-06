from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXECUTA_DIR = ROOT / "anna" / "executas" / "verigate-authority"
DIST = EXECUTA_DIR / "dist"
SMOKE_SCRIPT = ROOT / "anna" / "smoke_binary.py"
TOOL_ID = "tool-rinat-verigate-authority-2um8gwhw"


def verify_checksum(archive: Path) -> str:
    checksum_path = Path(str(archive) + ".sha256")
    if not checksum_path.is_file():
        raise SystemExit(f"checksum file missing: {checksum_path.name}")
    fields = checksum_path.read_text(encoding="utf-8").strip().split(maxsplit=1)
    if len(fields) != 2 or fields[1].lstrip("*") != archive.name:
        raise SystemExit(f"invalid checksum file for {archive.name}")
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual.lower() != fields[0].lower():
        raise SystemExit(f"SHA-256 mismatch for {archive.name}")
    return actual


def read_package(archive: Path, target: str) -> tuple[dict, str, bytes]:
    windows = target == "windows-x86_64"
    if windows:
        if archive.suffix != ".zip":
            raise SystemExit("Windows package must be a .zip archive")
        with zipfile.ZipFile(archive) as package:
            names = package.namelist()
            if len(names) != 2 or "manifest.json" not in names:
                raise SystemExit(f"unexpected Windows archive layout: {names}")
            manifest = json.loads(package.read("manifest.json").decode("utf-8"))
            entrypoint = manifest.get("runtime", {}).get("binary", {}).get("entrypoint", {}).get("default")
            if not isinstance(entrypoint, str) or Path(entrypoint).name != entrypoint or entrypoint not in names:
                raise SystemExit(f"invalid Windows binary entrypoint: {entrypoint!r}")
            binary = package.read(entrypoint)
    else:
        if not archive.name.endswith(".tar.gz"):
            raise SystemExit("Unix package must be a .tar.gz archive")
        with tarfile.open(archive, "r:gz") as package:
            members = package.getmembers()
            names = [member.name for member in members]
            if len(names) != 2 or "manifest.json" not in names:
                raise SystemExit(f"unexpected Unix archive layout: {names}")
            manifest_member = package.extractfile("manifest.json")
            if manifest_member is None:
                raise SystemExit("archive manifest.json could not be read")
            manifest = json.loads(manifest_member.read().decode("utf-8"))
            entrypoint = manifest.get("runtime", {}).get("binary", {}).get("entrypoint", {}).get("default")
            if not isinstance(entrypoint, str) or Path(entrypoint).name != entrypoint or entrypoint not in names:
                raise SystemExit(f"invalid Unix binary entrypoint: {entrypoint!r}")
            binary_member = package.extractfile(entrypoint)
            if binary_member is None:
                raise SystemExit("archive entrypoint could not be read")
            binary = binary_member.read()
            binary_info = next(member for member in members if member.name == entrypoint)
            if not (binary_info.mode & 0o111):
                raise SystemExit("Unix binary entrypoint is not executable in the archive")

    if manifest.get("name") != TOOL_ID:
        raise SystemExit(f"distribution tool ID mismatch: {manifest.get('name')!r}")
    if not manifest.get("version") or not manifest.get("description"):
        raise SystemExit("distribution manifest is missing required fields")
    return manifest, entrypoint, binary


def verify_runner_target(target: str) -> None:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in {"amd64", "x64"}:
        machine = "x86_64"
    elif machine in {"aarch64"}:
        machine = "arm64"
    expected = {
        "linux-x86_64": ("linux", "x86_64"),
        "windows-x86_64": ("windows", "x86_64"),
        "darwin-arm64": ("darwin", "arm64"),
        "darwin-x86_64": ("darwin", "x86_64"),
    }
    if target not in expected:
        raise SystemExit(f"unsupported target: {target}")
    wanted_system, wanted_machine = expected[target]
    if system != wanted_system or machine != wanted_machine:
        raise SystemExit(
            f"runner mismatch: target={target}, actual={system}-{machine}"
        )


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python anna/smoke_package.py <target> <version>")
    target, version = sys.argv[1], sys.argv[2]
    verify_runner_target(target)

    tool = json.loads((EXECUTA_DIR / "executa.json").read_text(encoding="utf-8"))
    if version != tool.get("version"):
        raise SystemExit(
            f"version mismatch: requested={version}, executa.json={tool.get('version')}"
        )
    configured = tool["distribution"]["profiles"]["binary"]["binary_artifacts"].get(target)
    if not isinstance(configured, dict):
        raise SystemExit(f"target not declared in executa.json: {target}")

    archive_path = DIST / configured["path"].replace("{version}", version)
    if not archive_path.is_file():
        raise SystemExit(f"release package not found: {archive_path}")
    digest = verify_checksum(archive_path)
    manifest, entrypoint, binary = read_package(archive_path, target)
    if manifest.get("version") != version:
        raise SystemExit(
            f"archive version mismatch: expected={version}, got={manifest.get('version')}"
        )
    if entrypoint != configured.get("entrypoint"):
        raise SystemExit(
            f"entrypoint mismatch: archive={entrypoint}, executa.json={configured.get('entrypoint')}"
        )

    # Execute the binary copied out of the actual release archive, not the
    # pre-package PyInstaller output. Never extract untrusted archive paths.
    with tempfile.TemporaryDirectory(prefix="verigate-packaged-smoke-") as temp_dir:
        extracted = Path(temp_dir) / entrypoint
        extracted.write_bytes(binary)
        if os.name == "posix":
            extracted.chmod(0o755)
        result = subprocess.run(
            [sys.executable, str(SMOKE_SCRIPT), str(extracted), version],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        if result.returncode != 0:
            raise SystemExit(
                f"packaged binary smoke test failed with exit code {result.returncode}"
            )

    print(
        f"packaged artifact passed: target={target}, version={version}, "
        f"entrypoint={entrypoint}, sha256={digest}"
    )


if __name__ == "__main__":
    main()
