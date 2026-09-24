"""Cryptographic binding for external state/preconditions at execution time."""
from __future__ import annotations
import hashlib
import json
from typing import Any

def canonical_external_state(action: dict[str, Any]) -> dict[str, Any]:
    metadata = action.get("metadata") if isinstance(action, dict) else None
    binding = metadata.get("external_state") if isinstance(metadata, dict) else None
    if not isinstance(binding, dict) or not binding:
        return {}
    return {str(k): binding[k] for k in sorted(binding)}

def external_state_digest(action: dict[str, Any]) -> str:
    payload = canonical_external_state(action)
    data = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()

def validate_external_state_binding(binding: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(binding, dict):
        return False, "external state binding must be an object"
    if not binding:
        return True, "no external state binding"
    if not isinstance(binding.get("kind"), str) or not binding["kind"].strip():
        return False, "external state binding is missing kind"
    if not isinstance(binding.get("reference"), str) or not binding["reference"].strip():
        return False, "external state binding is missing reference"
    digest = binding.get("digest")
    if not isinstance(digest, str) or len(digest) != 64:
        return False, "external state binding has invalid digest"
    try:
        int(digest, 16)
    except ValueError:
        return False, "external state binding digest is not hexadecimal"
    return True, "external state binding is valid"

def verify_external_state_binding(expected: dict[str, Any], action: dict[str, Any]) -> tuple[bool, str]:
    actual = canonical_external_state(action)
    if expected != actual:
        return False, "external state binding drift"
    return validate_external_state_binding(expected)
