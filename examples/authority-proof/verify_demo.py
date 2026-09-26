#!/usr/bin/env python3
"""Offline demo of third-party Verigate authority-proof verification."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / "examples" / "authority-proof" / "authority-proof.json"
PUBLIC_KEY = ROOT / "examples" / "authority-proof" / "issuer.pub"


def run(proof: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "cli.py",
            "verify",
            str(proof),
            "--public-key",
            str(PUBLIC_KEY),
            "--format",
            "text",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    if not PROOF.exists() or not PUBLIC_KEY.exists():
        print("portable proof fixture is missing", file=sys.stderr)
        return 2

    valid = run(PROOF)
    print("=== ORIGINAL PROOF ===")
    print(valid.stdout, end="")
    if valid.returncode != 0 or "RESULT: VALID" not in valid.stdout:
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        tampered = Path(tmp) / "tampered.json"
        document = json.loads(PROOF.read_text(encoding="utf-8"))
        document["package"]["agent_id"] = "tampered-agent"
        tampered.write_text(json.dumps(document), encoding="utf-8")
        invalid = run(tampered)
        print("\n=== TAMPERED PROOF ===")
        print(invalid.stdout, end="")
        if invalid.returncode == 0 or "RESULT: INVALID" not in invalid.stdout:
            return 1

    print("\nPortable proof demo: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
