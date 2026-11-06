"""Minimal shared stdio frame writer for the vendored Anna Executa storage client."""
from __future__ import annotations
import json
import sys
import threading

PROTOCOL_VERSION_V2 = "2.0"
_WRITE_LOCK = threading.Lock()
MAX_STDIO_MESSAGE_BYTES = 512 * 1024

def _write_frame(msg: dict, *, stdout=None) -> None:
    if stdout is None:
        stdout = sys.stdout
    payload = json.dumps(msg, ensure_ascii=False)
    if len(payload.encode("utf-8")) > MAX_STDIO_MESSAGE_BYTES:
        raise ValueError("JSON-RPC frame exceeds 512 KiB")
    with _WRITE_LOCK:
        stdout.write(payload + "\n")
        stdout.flush()
