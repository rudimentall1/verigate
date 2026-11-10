"""Canonical digest of the exact wire artifact authorized for execution."""
from __future__ import annotations
import hashlib, json
from typing import Any

def canonical_execution_artifact(action: dict[str, Any]) -> dict[str, Any]:
    metadata=action.get("metadata") if isinstance(action,dict) else None
    if not isinstance(metadata,dict): return {}
    tx=metadata.get("evm_transaction")
    if isinstance(tx,dict): return {"kind":"evm","artifact":{str(k):tx[k] for k in sorted(tx)}}
    raw=metadata.get("solana_transaction")
    if isinstance(raw,str): return {"kind":"solana","artifact":{"serialized_transaction":raw}}
    request=metadata.get("execution_request")
    if isinstance(request,dict): return {"kind":"generic","artifact":{str(k):request[k] for k in sorted(request)}}
    return {}

def execution_artifact_digest(action: dict[str, Any]) -> str:
    payload=canonical_execution_artifact(action)
    data=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()

def verify_execution_artifact(expected: dict[str,Any], action: dict[str,Any]) -> tuple[bool,str]:
    if expected != canonical_execution_artifact(action): return False,"execution artifact drift"
    return True,"execution artifact matches authorization"
