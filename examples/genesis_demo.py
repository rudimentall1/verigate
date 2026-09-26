#!/usr/bin/env python3
"""Genesis 2.0 judge demo: lifecycle contract, independent proof, and tamper rejection."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / "examples" / "authority-proof" / "authority-proof.json"
PUBLIC_KEY = ROOT / "examples" / "authority-proof" / "issuer.pub"
VERIFIER = ROOT / "tools" / "verigate_proof_verifier.py"
LIFECYCLE_TEST = (
    "tests.test_genesis_lifecycle.GenesisLifecycleTest."
    "test_full_genesis_lifecycle_reuses_enforcement_and_proof_boundaries"
)


def verify(proof: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER), str(proof), "--public-key", str(PUBLIC_KEY)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    required = (PROOF, PUBLIC_KEY, VERIFIER)
    if not all(path.exists() for path in required):
        print("Genesis 2.0 demo fixture is missing", file=sys.stderr)
        return 2

    print("==============================================================")
    print("VERIGATE | GENESIS 2.0 END-TO-END DEMO")
    print("==============================================================")
    print("1) Agent -> Intent -> Authority -> Authorization")
    print("2) Authorization -> Execution -> Observation")
    print("3) Outcome -> Learning -> Post-learning Authority")
    print("4) Portable proof -> runtime-independent verification")
    print("5) Tamper -> independent rejection")
    print("")

    print("=== LIVE LIFECYCLE CONTRACT ===")
    lifecycle = subprocess.run(
        [sys.executable, "-m", "unittest", LIFECYCLE_TEST, "-v"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    print(lifecycle.stdout, end="")
    if lifecycle.stderr:
        print(lifecycle.stderr, end="", file=sys.stderr)
    if lifecycle.returncode != 0:
        print("GENESIS 2.0 DEMO: FAIL", file=sys.stderr)
        return 1

    print("=== INDEPENDENT PROOF VERIFIER ===")
    valid = verify(PROOF)
    print(valid.stdout, end="")
    if valid.returncode != 0 or "RESULT: VALID" not in valid.stdout:
        print("Independent proof verification failed.", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="verigate-genesis-") as tmp:
        tampered = Path(tmp) / "tampered.json"
        document = json.loads(PROOF.read_text(encoding="utf-8"))
        document["package"]["agent_id"] = "tampered-agent"
        tampered.write_text(
            json.dumps(document, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

        print("\n=== ADVERSARIAL TAMPER ===")
        invalid = verify(tampered)
        print(invalid.stdout, end="")
        if invalid.returncode == 0 or "RESULT: INVALID" not in invalid.stdout:
            print("Tampered proof was not rejected.", file=sys.stderr)
            return 1

    print("\nGENESIS 2.0 DEMO: PASS")
    print("Runtime lifecycle passed; exported proof verified offline; tampering was rejected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
