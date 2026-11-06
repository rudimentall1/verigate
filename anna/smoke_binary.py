from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ALLOWED_TYPES = {"string", "integer", "number", "boolean", "array", "object"}


def check_manifest(manifest: dict) -> None:
    """Mirror Anna Executa protocol-v2 describe and APS capability requirements."""
    for field in ("name", "version", "description"):
        if not isinstance(manifest.get(field), str) or not manifest[field]:
            raise SystemExit(f"describe: missing or empty required field '{field}'")
    capabilities = set(manifest.get("host_capabilities") or [])
    if not {"aps.scope.app.read", "aps.scope.app.write"}.issubset(capabilities):
        raise SystemExit("describe: App-scoped APS read/write capabilities are required")
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

    for privileged in ("verigate_authorize_payment", "verigate_consume_execution_authorization"):
        tool = next((item for item in tools if item.get("name") == privileged), None)
        names = {item.get("name"): item for item in (tool or {}).get("parameters", [])}
        if tool is None or not names.get("confirmation_nonce", {}).get("required"):
            raise SystemExit(f"describe: {privileged} must require an App UI confirmation nonce")


def main() -> None:
    if len(sys.argv) not in {2, 3}:
        raise SystemExit("usage: python anna/smoke_binary.py <executable> [expected-version]")
    executable = Path(sys.argv[1]).resolve()
    expected_version = sys.argv[2] if len(sys.argv) == 3 else None
    if not executable.exists():
        raise SystemExit(f"binary not found: {executable}")

    with tempfile.TemporaryDirectory(prefix="verigate-anna-smoke-") as data_dir:
        smoke_env = {**os.environ, "VERIGATE_ANNA_DATA_DIR": data_dir}
        proc = subprocess.Popen(
            [str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", env=smoke_env,
        )

    stdout_lines: queue.Queue[str | None] = queue.Queue()

    def collect_stdout() -> None:
        try:
            for line in proc.stdout:
                stdout_lines.put(line)
        finally:
            stdout_lines.put(None)

    threading.Thread(target=collect_stdout, name="anna-smoke-stdout", daemon=True).start()

    def send(frame: dict | str) -> None:
        proc.stdin.write((frame if isinstance(frame, str) else json.dumps(frame)) + "\n")
        proc.stdin.flush()

    def recv(timeout: float = 10.0) -> dict:
        try:
            line = stdout_lines.get(timeout=timeout)
        except queue.Empty as exc:
            raise SystemExit(f"timed out waiting {timeout:.1f}s for a JSON-RPC response") from exc
        if line is None:
            raise SystemExit("process closed stdout before returning the expected JSON-RPC response")
        return json.loads(line)

    def invoke_with_storage(req_id: int, params: dict, approval: dict | None, app_context: bool) -> dict:
        send({"jsonrpc": "2.0", "id": req_id, "method": "invoke", "params": params})
        while True:
            msg = recv()
            method = msg.get("method")
            if method == "storage/get":
                rpc_params = msg.get("params") or {}
                if rpc_params.get("scope") != "app" or not app_context:
                    send({"jsonrpc": "2.0", "id": msg["id"], "error": {
                        "code": -32021, "message": "app-scoped storage unavailable outside App context"
                    }})
                else:
                    send({"jsonrpc": "2.0", "id": msg["id"], "result": {
                        "value": approval, "etag": "smoke-approval-etag", "exists": True
                    }})
            elif method == "storage/delete":
                rpc_params = msg.get("params") or {}
                if (not app_context or rpc_params.get("scope") != "app"
                        or rpc_params.get("if_match") != "smoke-approval-etag"):
                    send({"jsonrpc": "2.0", "id": msg["id"], "error": {
                        "code": -32023, "message": "approval ETag mismatch"
                    }})
                else:
                    send({"jsonrpc": "2.0", "id": msg["id"], "result": {"deleted": True}})
            elif msg.get("id") == req_id:
                return msg

    try:
        # 0. Negotiate protocol v2 before using APS reverse RPC.
        send({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
        initialized = recv()
        init_result = initialized.get("result", {})
        if init_result.get("protocolVersion") != "2.0" or init_result.get("capabilities", {}).get("storage", {}).get("kv") is not True:
            raise SystemExit(f"protocol-v2 APS initialization failed: {initialized}")
        send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

        # 1. describe from a cold start: Anna allows 5 s.
        started = time.monotonic()
        send({"jsonrpc": "2.0", "id": 1, "method": "describe"})
        described = recv()
        elapsed = time.monotonic() - started
        if described.get("id") != 1 or "result" not in described:
            raise SystemExit(f"describe failed or returned the wrong ID: {described}")
        check_manifest(described["result"])
        if expected_version and described["result"].get("version") != expected_version:
            raise SystemExit(
                f"binary version mismatch: expected {expected_version}, "
                f"described {described['result'].get('version')!r}"
            )
        if elapsed > 5.0:
            raise SystemExit(f"describe took {elapsed:.1f}s, Anna's limit is 5s")
        if elapsed > 3.0:
            print(f"warning: describe took {elapsed:.1f}s (limit 5s)")

        # 1b. A second describe with a string ID proves the process remains alive
        # and preserves JSON-RPC request IDs of different types.
        send({"jsonrpc": "2.0", "id": "describe-repeat", "method": "describe"})
        repeated = recv()
        if repeated.get("id") != "describe-repeat" or repeated.get("result") != described["result"]:
            raise SystemExit(f"repeated describe failed or returned the wrong ID: {repeated}")

        # 2. health
        send({"jsonrpc": "2.0", "id": 2, "method": "health"})
        health = recv()
        if health.get("result", {}).get("status") != "ready":
            raise SystemExit(f"health check failed: {health}")

        # 3. a real signed decision
        send({"jsonrpc": "2.0", "id": 3, "method": "invoke", "params": {
            "tool": "verigate_check",
            "arguments": {
                "agent_id": "anna-cloud-smoke", "payee": "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed",
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

        # 3b. a malformed recipient must be BLOCKed (regression: "0xabc" used to be ALLOWed)
        send({"jsonrpc": "2.0", "id": 31, "method": "invoke", "params": {
            "tool": "verigate_check",
            "arguments": {"agent_id": "anna-cloud-smoke", "payee": "0xabc",
                          "asset": "USDC", "network": "base", "amount": 10.5},
        }})
        bad = recv().get("result", {})
        bad_decision = (bad.get("data", {}).get("decision_receipt", {}).get("payload", {})
                        .get("decision", {}).get("decision"))
        if bad.get("success") is not True or bad_decision != "BLOCK":
            raise SystemExit(f"malformed recipient must be BLOCK, got: {bad}")

        # 3c. the policy summary tool answers
        send({"jsonrpc": "2.0", "id": 32, "method": "invoke", "params": {"tool": "verigate_policy_summary", "arguments": {}}})
        summary = recv().get("result", {})
        if summary.get("success") is not True or not summary.get("data", {}).get("payee_validation"):
            raise SystemExit(f"policy summary failed: {summary}")

        # 3d. A direct chat/agent invocation has no App-scoped approval and must fail closed.
        direct = invoke_with_storage(33, {
            "tool": "verigate_authorize_payment",
            "arguments": {
                "agent_id": "anna-binary-wallet-smoke",
                "payee": "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed",
                "asset": "USDC", "network": "base", "amount": 25,
                "confirmation_nonce": "d" * 48,
            },
            "context": {"invoke_id": "smoke-direct"},
        }, None, False)
        direct_result = direct.get("result", {})
        if direct_result.get("success") is not False or direct_result.get("data", {}).get("execution_authorization"):
            raise SystemExit(f"direct tool call bypassed App UI approval: {direct}")

        # 3e. Simulate the App-context storage round-trip after a real UI click.
        nonce = "a" * 48
        now_ms = int(time.time() * 1000)
        approval = {
            "version": 1,
            "kind": "payment_authorization",
            "nonce": nonce,
            "agent_id": "anna-binary-wallet-smoke",
            "payee": "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed",
            "asset": "USDC",
            "network": "base",
            "amount": 25,
            "resource": "invoice smoke",
            "created_at_ms": now_ms,
            "expires_at_ms": now_ms + 60_000,
        }
        authorized = invoke_with_storage(34, {
            "tool": "verigate_authorize_payment",
            "arguments": {
                "agent_id": approval["agent_id"],
                "payee": approval["payee"],
                "asset": approval["asset"],
                "network": approval["network"],
                "amount": approval["amount"],
                "resource": approval["resource"],
                "confirmation_nonce": nonce,
            },
            "context": {"invoke_id": "smoke-app-context", "app_id": "verigate-test-app"},
        }, approval, True).get("result", {})
        if authorized.get("success") is not True:
            raise SystemExit(f"App-scoped wallet authorization failed: {authorized}")
        authorization = authorized.get("data", {}).get("execution_authorization")
        if not isinstance(authorization, dict):
            raise SystemExit(f"wallet authorization artifact missing: {authorized}")

        # A direct chat invocation cannot consume the permission, even if it knows the signed JSON.
        direct_consume_nonce = "c" * 48
        direct_consume = invoke_with_storage(35, {
            "tool": "verigate_consume_execution_authorization",
            "arguments": {
                "authorization_json": json.dumps(authorization),
                "confirmation_nonce": direct_consume_nonce,
            },
            "context": {"invoke_id": "smoke-direct-consume"},
        }, None, False).get("result", {})
        if direct_consume.get("success") is not False:
            raise SystemExit(f"direct wallet consume bypassed App UI approval: {direct_consume}")

        # The explicit wallet button writes a second one-time approval bound to the exact signed transaction.
        wallet_nonce = "b" * 48
        wallet_now_ms = int(time.time() * 1000)
        action = authorization["payload"]["action"]
        tx_approval = action["metadata"]["evm_transaction"]
        wallet_approval = {
            "version": 1,
            "kind": "wallet_submission",
            "nonce": wallet_nonce,
            "authorization_id": authorization["payload"]["authorization_id"],
            "agent_id": action["agent_id"],
            "target": action["target"],
            "asset": action["asset"],
            "network": action["network"],
            "amount": action["amount"],
            "resource": action.get("resource") or "",
            "chain_id": tx_approval["chain_id"],
            "to": tx_approval["to"],
            "value_wei": tx_approval["value_wei"],
            "data": tx_approval["data"],
            "created_at_ms": wallet_now_ms,
            "expires_at_ms": wallet_now_ms + 60_000,
        }
        consumed = invoke_with_storage(36, {
            "tool": "verigate_consume_execution_authorization",
            "arguments": {
                "authorization_json": json.dumps(authorization),
                "confirmation_nonce": wallet_nonce,
            },
            "context": {"invoke_id": "smoke-wallet-click", "app_id": "verigate-test-app"},
        }, wallet_approval, True).get("result", {})
        handoff = consumed.get("data", {})
        tx = handoff.get("transaction", {})
        if (consumed.get("success") is not True or handoff.get("consumed") is not True
                or handoff.get("transaction_submitted") is not False
                or tx.get("chain_id") != 8453
                or tx.get("to", "").lower() != "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
                or not tx.get("data", "").startswith("0xa9059cbb")):
            raise SystemExit(f"ExecutionRouter wallet hand-off failed: {consumed}")

        # Even a second fresh UI approval cannot replay an already consumed authorization.
        replay_nonce = "e" * 48
        replay_now_ms = int(time.time() * 1000)
        replay_approval = {**wallet_approval, "nonce": replay_nonce,
                           "created_at_ms": replay_now_ms, "expires_at_ms": replay_now_ms + 60_000}
        replay = invoke_with_storage(37, {
            "tool": "verigate_consume_execution_authorization",
            "arguments": {
                "authorization_json": json.dumps(authorization),
                "confirmation_nonce": replay_nonce,
            },
            "context": {"invoke_id": "smoke-replay", "app_id": "verigate-test-app"},
        }, replay_approval, True).get("result", {})
        if replay.get("success") is not False:
            raise SystemExit(f"one-time authorization replay was not rejected: {replay}")

        # 4. error handling must not kill the process
        send("this is not json")
        if recv().get("error", {}).get("code") != -32700:
            raise SystemExit("bad JSON must return -32700")
        send({"jsonrpc": "2.0", "id": 4, "method": "invoke", "params": {"tool": "nope", "arguments": {}}})
        if recv().get("error", {}).get("code") != -32601:
            raise SystemExit("unknown tool must return -32601")
        send({"jsonrpc": "2.0", "id": 5, "method": "invoke", "params": {"tool": "verigate_check", "arguments": {}}})
        invalid_params = recv()
        if invalid_params.get("id") != 5 or invalid_params.get("error", {}).get("code") != -32602:
            raise SystemExit("missing arguments must return -32602 with the matching ID")

        # 5. The process must recover after protocol and business errors.
        send({"jsonrpc": "2.0", "id": "describe-after-errors", "method": "describe"})
        recovered = recv()
        if recovered.get("id") != "describe-after-errors" or recovered.get("result", {}).get("version") != described["result"].get("version"):
            raise SystemExit(f"describe did not recover after errors: {recovered}")
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise SystemExit("binary did not exit on stdin EOF")

    if proc.returncode != 0:
        raise SystemExit(f"binary exited with {proc.returncode}\nSTDERR:\n{proc.stderr.read()}")
    print(f"binary smoke test passed: describe in {elapsed:.1f}s, decision={decision}, signed=yes, app_scope_approval=consumed_once, wallet_handoff=consumed_once")


if __name__ == "__main__":
    main()