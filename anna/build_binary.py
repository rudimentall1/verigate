from __future__ import annotations

import shutil
from pathlib import Path

from PyInstaller.__main__ import run

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "anna" / "executas" / "verigate-authority" / "verigate_authority_plugin.py"
DIST = ROOT / "anna" / "executas" / "verigate-authority" / "dist"


def main() -> None:
    DIST.mkdir(parents=True, exist_ok=True)
    work = ROOT / "anna" / ".pyinstaller"
    spec = ROOT / "anna" / ".pyinstaller-spec"
    if work.exists():
        shutil.rmtree(work)
    if spec.exists():
        shutil.rmtree(spec)

    import os
    separator = os.pathsep
    run([
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name", "verigate-authority",
        "--paths", str(ROOT),
        "--collect-submodules", "core",
        "--collect-submodules", "attest",
        "--add-data", f"{ROOT / 'policies' / 'default.yaml'}{separator}policies",
        "--distpath", str(DIST),
        "--workpath", str(work),
        "--specpath", str(spec),
        str(ENTRY),
    ])


if __name__ == "__main__":
    main()
