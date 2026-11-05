from __future__ import annotations

import hashlib
import json
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXECUTA_DIR = ROOT / "anna" / "executas" / "verigate-authority"
DIST = EXECUTA_DIR / "dist"

# The platform-minted ID is the identity of this published Executa. The
# local development ID in executa.json is intentionally different.
PLATFORM_TOOL_ID = "tool-rinat-verigate-authority-2um8gwhw"
DISPLAY_NAME = "Verigate Authority"


def build_package_manifest(version: str, description: str, entrypoint: str, windows: bool) -> dict:
    binary_runtime = {"entrypoint": {"default": entrypoint}}
    if not windows:
        binary_runtime["permissions"] = {entrypoint: "0o755"}
    return {
        "name": PLATFORM_TOOL_ID,
        "display_name": DISPLAY_NAME,
        "version": version,
        "description": description,
        "runtime": {"binary": binary_runtime},
    }


def verify_archive(archive: Path, entrypoint: str, windows: bool) -> None:
    """Fail packaging unless both the runnable binary and distribution manifest exist."""
    if windows:
        with zipfile.ZipFile(archive) as packaged:
            names = set(packaged.namelist())
            if "manifest.json" not in names or entrypoint not in names:
                raise SystemExit(f"invalid archive layout: {sorted(names)}")
            manifest = json.loads(packaged.read("manifest.json").decode("utf-8"))
    else:
        with tarfile.open(archive, "r:gz") as packaged:
            names = set(packaged.getnames())
            if "manifest.json" not in names or entrypoint not in names:
                raise SystemExit(f"invalid archive layout: {sorted(names)}")
            member = packaged.extractfile("manifest.json")
            if member is None:
                raise SystemExit("archive manifest.json could not be read")
            manifest = json.loads(member.read().decode("utf-8"))

    configured = manifest.get("runtime", {}).get("binary", {}).get("entrypoint", {}).get("default")
    if configured != entrypoint:
        raise SystemExit(f"manifest entrypoint mismatch: expected {entrypoint!r}, got {configured!r}")
    if not manifest.get("version") or not manifest.get("name") or not manifest.get("description"):
        raise SystemExit("distribution manifest is missing name, version, or description")


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python anna/package_binary.py <target> <version>")
    target, version = sys.argv[1], sys.argv[2]
    tool = json.loads((EXECUTA_DIR / "executa.json").read_text(encoding="utf-8"))
    expected = tool["version"]
    if version != expected:
        raise SystemExit(f"version mismatch: workflow={version}, executa.json={expected}")

    windows = target == "windows-x86_64"
    if target not in {"darwin-arm64", "darwin-x86_64", "linux-x86_64", "windows-x86_64"}:
        raise SystemExit(f"unsupported target: {target}")

    binary = DIST / ("verigate-authority.exe" if windows else "verigate-authority")
    if not binary.is_file():
        raise SystemExit(f"built binary not found: {binary}")

    archive_name = (
        f"verigate-authority-{version}-{target}.zip"
        if windows
        else f"verigate-authority-{version}-{target}.tar.gz"
    )
    archive = DIST / archive_name
    if archive.exists():
        archive.unlink()

    entrypoint = binary.name
    package_manifest = build_package_manifest(
        version=version,
        description=(
            "Evaluates an agent action against Verigate's deterministic policy and returns "
            "a signed ALLOW/WARN/BLOCK policy decision. It does not sign, submit, broadcast, "
            "or execute a blockchain transaction."
        ),
        entrypoint=entrypoint,
        windows=windows,
    )
    manifest_bytes = (json.dumps(package_manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

    if windows:
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as packaged:
            packaged.write(binary, arcname=entrypoint)
            packaged.writestr("manifest.json", manifest_bytes)
    else:
        with tarfile.open(archive, "w:gz") as packaged:
            packaged.add(binary, arcname=entrypoint)
            info = tarfile.TarInfo("manifest.json")
            info.size = len(manifest_bytes)
            info.mode = 0o644
            import io
            packaged.addfile(info, io.BytesIO(manifest_bytes))

    verify_archive(archive, entrypoint, windows)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")

    print(f"Verified package: {archive}")
    print("Archive root: manifest.json, " + entrypoint)
    print(f"SHA-256: {digest}")
    print(f"Size: {archive.stat().st_size} bytes")


if __name__ == "__main__":
    main()
