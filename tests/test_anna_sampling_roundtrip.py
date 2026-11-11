"""Local wire-level acceptance for Anna Executa reverse Sampling.

The host is emulated over stdio; no Anna account, CU quota, or network call is used.
"""
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "anna" / "executas" / "verigate-authority" / "verigate_authority_plugin.py"


class AnnaSamplingRoundTripTest(unittest.TestCase):
    def test_ui_executa_sampling_host_llm_roundtrip(self):
        with tempfile.TemporaryDirectory(prefix="verigate-sampling-") as tmp:
            env = {
                **os.environ,
                "VERIGATE_ANNA_DATA_DIR": str(Path(tmp) / "state"),
                "PYTHONPATH": str(ROOT),
            }
            proc = subprocess.Popen(
                [sys.executable, str(PLUGIN)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
                env=env,
            )
            frames: queue.Queue = queue.Queue()

            def _reader():
                assert proc.stdout is not None
                for line in proc.stdout:
                    if line.strip():
                        try:
                            frames.put(json.loads(line))
                        except json.JSONDecodeError as exc:
                            frames.put(exc)
                            return
                frames.put(None)

            thread = threading.Thread(target=_reader, daemon=True)
            thread.start()

            def _send(frame: dict):
                assert proc.stdin is not None
                proc.stdin.write(json.dumps(frame, ensure_ascii=False) + "\n")
                proc.stdin.flush()

            def _read():
                try:
                    value = frames.get(timeout=15)
                except queue.Empty as exc:
                    stderr = ""
                    if proc.stderr is not None:
                        try:
                            stderr = proc.stderr.read(2000)
                        except Exception:
                            pass
                    raise AssertionError("Timed out waiting for Executa frame: " + stderr) from exc
                if isinstance(value, Exception):
                    raise value
                if value is None:
                    stderr = proc.stderr.read() if proc.stderr is not None else ""
                    raise AssertionError("Executa closed stdout unexpectedly: " + stderr)
                return value

            try:
                _send({
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {"protocolVersion": "2.0"},
                })
                initialized = _read()
                self.assertEqual(initialized["id"], 1)
                self.assertEqual(initialized["result"]["protocolVersion"], "2.0")
                self.assertIn("sampling", initialized["result"]["client_capabilities"])
                self.assertIn("storage", initialized["result"]["client_capabilities"])

                _send({
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "invoke",
                    "params": {
                        "tool": "verigate_ai_review",
                        "arguments": {
                            "system_prompt": "You are a safe test model.",
                            "prompt": "Return the word SAFE.",
                            "max_tokens": 64,
                        },
                        "context": {"invoke_id": "invocation-roundtrip-123"},
                    },
                })

                reverse = _read()
                self.assertEqual(reverse["method"], "sampling/createMessage")
                self.assertEqual(reverse["params"]["maxTokens"], 64)
                self.assertEqual(
                    reverse["params"]["messages"][0]["content"]["text"],
                    "Return the word SAFE.",
                )
                self.assertEqual(
                    reverse["params"]["context"]["invoke_id"],
                    "invocation-roundtrip-123",
                )

                _send({
                    "jsonrpc": "2.0",
                    "id": reverse["id"],
                    "result": {
                        "role": "assistant",
                        "content": {"type": "text", "text": "SAFE"},
                        "model": "mock-host-model",
                        "stopReason": "endTurn",
                        "usage": {"inputTokens": 4, "outputTokens": 1, "totalTokens": 5},
                    },
                })
                completed = _read()
                self.assertEqual(completed["id"], 7)
                self.assertTrue(completed["result"]["success"], completed)
                self.assertEqual(completed["result"]["data"]["text"], "SAFE")
                self.assertEqual(completed["result"]["data"]["model"], "mock-host-model")

                _send({"jsonrpc": "2.0", "id": 9, "method": "shutdown", "params": {}})
                shutdown = _read()
                self.assertEqual(shutdown["id"], 9)
                proc.stdin.close()
                self.assertEqual(proc.wait(timeout=10), 0)
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=5)
                if proc.stdin and not proc.stdin.closed:
                    proc.stdin.close()
                if proc.stdout and not proc.stdout.closed:
                    proc.stdout.close()
                if proc.stderr and not proc.stderr.closed:
                    proc.stderr.close()



class AnnaStorageTransportFailureTest(unittest.IsolatedAsyncioTestCase):
    async def test_timed_out_request_discards_late_host_response(self):
        sys.path.insert(0, str(ROOT / "anna" / "executas" / "verigate-authority"))
        from executa_sdk.storage import StorageClient, StorageError, STORAGE_ERR_TIMEOUT

        frames = []
        client = StorageClient(write_frame=frames.append)

        with self.assertRaises(StorageError) as raised:
            await client.get("verigate/approvals/test", scope="app", timeout=0.001)

        self.assertEqual(raised.exception.code, STORAGE_ERR_TIMEOUT)
        self.assertEqual(len(frames), 1)
        request_id = frames[0]["id"]
        self.assertNotIn(request_id, client._pending)

        # A host reply arriving after the client deadline is stale and must
        # not resolve a later invocation or resurrect the expired request.
        handled = client.dispatch_response({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"value": {"approved": True}, "exists": True},
        })
        self.assertFalse(handled)
        self.assertEqual(client._pending, {})

    async def test_conditional_delete_conflict_is_preserved_as_storage_error(self):
        sys.path.insert(0, str(ROOT / "anna" / "executas" / "verigate-authority"))
        from executa_sdk.storage import (
            StorageClient,
            StorageError,
            STORAGE_ERR_PRECONDITION_FAILED,
        )

        frames = []
        client = StorageClient(write_frame=frames.append)
        task = asyncio.create_task(client.delete(
            "verigate/approvals/test",
            scope="app",
            if_match="etag-read",
            timeout=1.0,
        ))
        for _ in range(20):
            if frames:
                break
            await asyncio.sleep(0)
        self.assertEqual(len(frames), 1)
        request = frames[0]
        self.assertEqual(request["method"], "storage/delete")
        self.assertEqual(request["params"]["if_match"], "etag-read")

        self.assertTrue(client.dispatch_response({
            "jsonrpc": "2.0",
            "id": request["id"],
            "error": {
                "code": STORAGE_ERR_PRECONDITION_FAILED,
                "message": "ETag does not match",
            },
        }))
        with self.assertRaises(StorageError) as raised:
            await task
        self.assertEqual(raised.exception.code, STORAGE_ERR_PRECONDITION_FAILED)
        self.assertIn("ETag does not match", raised.exception.message)


if __name__ == "__main__":
    unittest.main()
