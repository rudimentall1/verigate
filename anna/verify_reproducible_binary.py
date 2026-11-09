from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "anna" / "executas" / "verigate-authority" / "dist"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_reproducible_binary(binary: Path) -> tuple[str, str]:
    """Build the same commit twice and fail unless the executable bytes match."""
    if os.environ.get("PYTHONHASHSEED") != "0":
        raise SystemExit("PYTHONHASHSEED must be set to 0 by the workflow")
    raw_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    try:
        epoch = int(raw_epoch) if raw_epoch is not None else -1
    except ValueError as exc:
        raise SystemExit("SOURCE_DATE_EPOCH must be a non-negative integer") from exc
    if epoch < 0:
        raise SystemExit("SOURCE_DATE_EPOCH must be a non-negative integer")

    build_script = ROOT / "anna" / "build_binary.py"
    if not build_script.is_file():
        raise SystemExit(f"build script not found: {build_script}")

    env = os.environ.copy()
    with tempfile.TemporaryDirectory(prefix="verigate-reproducible-build-") as temp:
        first_copy = Path(temp) / binary.name
        for iteration in (1, 2):
            print(f"=== Reproducibility build {iteration}/2 ===", flush=True)
            subprocess.run(
                [sys.executable, str(build_script)],
                cwd=ROOT,
                env=env,
                check=True,
            )
            if not binary.is_file():
                raise SystemExit(f"expected executable was not produced: {binary}")
            digest = sha256_file(binary)
            if iteration == 1:
                shutil.copy2(binary, first_copy)
                first_digest = digest
                print(f"build 1 SHA-256: {first_digest}", flush=True)
            else:
                second_digest = digest
                print(f"build 2 SHA-256: {second_digest}", flush=True)

        copied_digest = sha256_file(first_copy)
        if copied_digest != first_digest:
            raise SystemExit("temporary copy of first build changed unexpectedly")
        if first_digest != second_digest:
            raise SystemExit(
                "REPRODUCIBILITY FAILURE: identical source and environment produced "
                f"different binaries ({first_digest} != {second_digest})"
            )

    print(f"REPRODUCIBILITY PASS: {binary.name} {first_digest}", flush=True)
    return first_digest, second_digest


def main() -> None:
    binary_name = "verigate-authority.exe" if os.name == "nt" else "verigate-authority"
    verify_reproducible_binary(DIST / binary_name)


if __name__ == "__main__":
    main()
