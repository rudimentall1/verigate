from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXECUTA_DIR = ROOT / "anna" / "executas" / "verigate-authority"
DIST = EXECUTA_DIR / "dist"


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: python anna/package_binary.py <target> <version>")
    target, version = sys.argv[1], sys.argv[2]
    expected = json.loads((EXECUTA_DIR / "executa.json").read_text(encoding="utf-8"))["version"]
    if version != expected:
        raise SystemExit(f"version mismatch: workflow={version}, executa.json={expected}")

    windows = target == "windows-x86_64"
    if target not in {"darwin-arm64", "darwin-x86_64", "linux-x86_64", "windows-x86_64"}:
        raise SystemExit(f"unsupported target: {target}")

    binary = DIST / ("verigate-authority.exe" if windows else "verigate-authority")
    if not binary.exists():
        raise SystemExit(f"built binary not found: {binary}")

    archive_name = f"verigate-authority-{version}-{target}.zip" if windows else f"verigate-authority-{version}-{target}.tar.gz"
    archive = DIST / archive_name
    if archive.exists():
        archive.unlink()

    if windows:
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(binary, arcname="verigate-authority.exe")
    else:
        with tarfile.open(archive, "w:gz") as tf:
            tf.add(binary, arcname="verigate-authority")

    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")
    print(archive)
    print(checksum)


if __name__ == "__main__":
    main()
