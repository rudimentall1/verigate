#!/usr/bin/env python3
"""Genesis 2.0 end-to-end portable proof demonstration."""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / "examples" / "authority-proof" / "authority-proof.json"
PUBLIC_KEY = ROOT / "examples" / "authority-proof" / "issuer.pub"
VERIFIER = ROOT / "tools" / "verigate_proof_verifier.py"

def run(proof: Path):
    return subprocess.run([sys.executable, str(VERIFIER), str(proof), "--public-key", str(PUBLIC_KEY)], cwd=ROOT, capture_output=True, text=True, check=False)

def main() -> int:
    if not PROOF.exists() or not PUBLIC_KEY.exists() or not VERIFIER.exists():
        print("Genesis 2.0 demo fixture is missing", file=sys.stderr); return 2
    print("=== GENESIS 2.0 PORTABLE AUTHORITY DEMO ===")
    print("[1] Agent -> Intent -> Authority -> Authorization")
    print("[2] Execution -> Outcome -> Learning -> Post-learning Authority")
    print("[3] Portable proof loaded from disk")
    print("[4] Verigate runtime is not required")
    valid = run(PROOF)
    print("\\n=== INDEPENDENT VERIFIER ===")
    print(valid.stdout, end="")
    if valid.returncode != 0 or "RESULT: VALID" not in valid.stdout:
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        tampered = Path(tmp) / "tampered.json"
        document = json.loads(PROOF.read_text(encoding="utf-8"))
        document["package"]["agent_id"] = "tampered-agent"
        tampered.write_text(json.dumps(document), encoding="utf-8")
        invalid = run(tampered)
        print("\\n=== TAMPER TEST ===")
        print(invalid.stdout, end="")
        if invalid.returncode == 0 or "RESULT: INVALID" not in invalid.stdout:
            return 1
    print("\\nGENESIS 2.0 DEMO: PASS")
    return 0

if __name__ == "__main__": raise SystemExit(main())
