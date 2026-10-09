from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ALLOWED_TYPES = {"string", "integer", "number", "boolean", "array", "object"}


def check_manifest(manifest: dict) -> None:
    """Mirror what Anna's `describe` handshake requires (Executa protocol 1.1)."""
    for field in ("name", "version", "description"):
        if not isinstance(manifest.get(field), str) or not manifest[field]:
            raise SystemExit(f"describe: missing or empty required field '{field}'")
    tools = manifest.get("tools")
    if not isinstance(tools, list) or not tools:
        raise SystemExit("describe: 'tools' must be a non-empty list")
    for tool in tools:
        for field in ("name", "description"):
            if not isinstance(tool.get(field), str) or not tool[field]:
                raise SystemExit(f"describe: tool missing '{field}': {tool}")
        params = tool.get("parameters", [])
        if not isinstance(params, list):
            raise SystemExit(
                f"describe: tool '{tool['name']}' parameters must be a LIST of "
                f"parameter objects, got {type(params).__name__}"
            )
        for param in params:
            if not isinstance(param.get("name"), str) or param.get("type") not in ALLOWED_TYPES:
                raise SystemExit(f"describe: bad parameter definition: {param}")
            if "required" in param and not isinstance(param["required"], bool):
                raise SystemExit(f"describe: 'required' must be boolean: {param}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python anna/smoke_binary.py <executable>")
    executable = Path(sys.argv[1]).resolve()
    if not executable.exists():
        raise SystemExit(f"binary not found: {executable}")

    proc = subprocess.Popen(
        [str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True,
    )

    def send(frame: dict | str) -> None:
        proc.stdin.write((frame if isinstance(frame, str) else json.dumps(frame)) + "\n")
        proc.stdin.flush()

    def recv() -> dict:
        line = proc.stdout.readline()
        if not line:
            raise SystemExit(f"no response; stderr:\n{proc.stderr.read()}")
        return json.loads(line)

    try:
        # 1. describe from a cold start: Anna allows 5 s.
        started = time.monotonic()
        send({"jsonrpc": "2.0", "id": 1, "method": "describe"})
        described = recv()
        elapsed = time.monotonic() - started
        if "result" not in described:
            raise SystemExit(f"describe failed: {described}")
        check_manifest(described["result"])
        if elapsed > 5.0:
            raise SystemExit(f"describe took {elapsed:.1f}s, Anna's limit is 5s")
        if elapsed > 3.0:
            print(f"warning: describe took {elapsed:.1f}s (limit 5s)")

        # 2. health
        send({"jsonrpc": "2.0", "id": 2, "method": "health"})
        health = recv()
        if health.get("result", {}).get("status") != "ready":
            raise SystemExit(f"health check failed: {health}")

        # 3. a real signed decision
        send({"jsonrpc": "2.0", "id": 3, "method": "invoke", "params": {
            "tool": "verigate_check",
            "arguments": {
                "agent_id": "anna-cloud-smoke", "payee": "0xMerchantDemo",
                "asset": "USDC", "network": "base", "amount": 10.5,
            },
        }})
        invoked = recv()
        result = invoked.get("result", {})
        if result.get("success") is not True:
            raise SystemExit(f"verigate_check failed: {invoked}")
        receipt = result.get("data", {}).get("decision_receipt", {})
        decision = receipt.get("payload", {}).get("decision", {}).get("decision")
        if decision not in {"ALLOW", "WARN", "BLOCK"} or not receipt.get("signature"):
            raise SystemExit(f"invalid signed decision response: {invoked}")

        # 4. error handling must not kill the process
        send("this is not json")
        if recv().get("error", {}).get("code") != -32700:
            raise SystemExit("bad JSON must return -32700")
        send({"jsonrpc": "2.0", "id": 4, "method": "invoke", "params": {"tool": "nope", "arguments": {}}})
        if recv().get("error", {}).get("code") != -32601:
            raise SystemExit("unknown tool must return -32601")
        send({"jsonrpc": "2.0", "id": 5, "method": "invoke", "params": {"tool": "verigate_check", "arguments": {}}})
        if recv().get("error", {}).get("code") != -32602:
            raise SystemExit("missing arguments must return -32602")
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise SystemExit("binary did not exit on stdin EOF")

    if proc.returncode != 0:
        raise SystemExit(f"binary exited with {proc.returncode}\nSTDERR:\n{proc.stderr.read()}")
    print(f"binary smoke test passed: describe in {elapsed:.1f}s, decision={decision}, signed=yes")


if __name__ == "__main__":
    main()