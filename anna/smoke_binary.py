from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python anna/smoke_binary.py <executable>")
    executable = Path(sys.argv[1]).resolve()
    if not executable.exists():
        raise SystemExit(f"binary not found: {executable}")

    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "health"},
        {"jsonrpc": "2.0", "id": 2, "method": "invoke", "params": {
            "tool": "verigate_check",
            "arguments": {
                "agent_id": "anna-cloud-smoke",
                "payee": "0xMerchantDemo",
                "asset": "USDC",
                "network": "base",
                "amount": 10.5
            }
        }}
    ]
    proc = subprocess.run(
        [str(executable)],
        input="".join(json.dumps(item) + "\n" for item in requests),
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(f"binary exited with {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")

    lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    if len(lines) != 2:
        raise SystemExit(f"expected 2 JSON-RPC responses, got {len(lines)}: {proc.stdout}")
    if lines[0].get("result", {}).get("status") != "ready":
        raise SystemExit(f"health check failed: {lines[0]}")

    result = lines[1].get("result", {})
    if result.get("success") is not True:
        raise SystemExit(f"verigate_check failed: {lines[1]}")

    receipt = result.get("data", {}).get("decision_receipt", {})
    payload = receipt.get("payload", {})
    decision = payload.get("decision", {}).get("decision")
    signature = receipt.get("signature")
    if decision not in {"ALLOW", "WARN", "BLOCK"} or not signature:
        raise SystemExit(f"invalid signed decision response: {lines[1]}")
    print(f"binary smoke test passed: decision={decision}, signed=yes")


if __name__ == "__main__":
    main()
