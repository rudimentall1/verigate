"""Self-contained, versioned ProofPackage export/import for offline verification.

A ProofPackage is a transport artifact, not a second proof format. It wraps
an existing signed evidence manifest so a third party can carry the complete
portable evidence bundle as one deterministic byte sequence and verify it
without SQLite, the Verigate API, or live authority state.
"""
from __future__ import annotations

import json
from typing import Any

from core.offline_verifier import verify_proof
from core.proof_engine import canonical, digest

PACKAGE_VERSION = 1
PACKAGE_MEDIA_TYPE = "application/vnd.verigate.proof-package+json"
PACKAGE_PROTOCOL = "verigate-proof-package-v1"


def _package_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise TypeError("manifest must be an object")
    manifest_payload = manifest.get("payload")
    if not isinstance(manifest_payload, dict):
        raise ValueError("proof package manifest payload is missing")
    nodes = manifest_payload.get("nodes")
    edges = manifest_payload.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValueError("proof package manifest graph is missing")
    inventory = [
        {
            "type": node.get("type"),
            "id": node.get("id"),
            "sha256": node.get("sha256"),
        }
        for node in nodes
    ]
    return {
        "package_version": PACKAGE_VERSION,
        "media_type": PACKAGE_MEDIA_TYPE,
        "protocol": PACKAGE_PROTOCOL,
        "proof_profile": manifest_payload.get("proof_profile"),
        "authorization_id": manifest_payload.get("authorization_id"),
        "intent_id": manifest_payload.get("intent_id"),
        "agent_id": manifest_payload.get("agent_id"),
        "graph_root_digest": manifest_payload.get("root_digest"),
        "node_inventory": inventory,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "manifest_sha256": digest(manifest),
        "manifest": manifest,
    }


def build_proof_package(manifest: dict[str, Any]) -> dict[str, Any]:
    """Wrap one signed evidence manifest in a deterministic package envelope."""
    payload = _package_payload(manifest)
    return {
        "package": payload,
        "package_sha256": digest(payload),
    }


def serialize_proof_package(package: dict[str, Any]) -> bytes:
    """Serialize a package canonically so the exact bytes are portable."""
    valid, reason = _validate_package_envelope(package)
    if not valid:
        raise ValueError(reason)
    return canonical(package)


def parse_proof_package(data: bytes | str) -> dict[str, Any]:
    """Parse JSON package bytes without consulting Verigate runtime state."""
    if isinstance(data, bytes):
        try:
            data = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("proof package is not valid UTF-8") from exc
    if not isinstance(data, str):
        raise TypeError("package data must be bytes or str")
    try:
        package = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ValueError("proof package is not valid JSON") from exc
    valid, reason = _validate_package_envelope(package)
    if not valid:
        raise ValueError(reason)
    return package


def _validate_package_envelope(package: Any) -> tuple[bool, str]:
    if not isinstance(package, dict):
        return False, "proof package must be an object"
    payload = package.get("package")
    package_sha256 = package.get("package_sha256")
    if not isinstance(payload, dict) or not isinstance(package_sha256, str):
        return False, "proof package envelope is incomplete"
    if payload.get("package_version") != PACKAGE_VERSION:
        return False, "unsupported proof package version"
    if payload.get("media_type") != PACKAGE_MEDIA_TYPE:
        return False, "unsupported proof package media type"
    if payload.get("protocol") != PACKAGE_PROTOCOL:
        return False, "unsupported proof package protocol"
    if digest(payload) != package_sha256:
        return False, "proof package digest mismatch"
    manifest = payload.get("manifest")
    if not isinstance(manifest, dict):
        return False, "proof package manifest is missing"
    manifest_payload = manifest.get("payload")
    if not isinstance(manifest_payload, dict):
        return False, "proof package manifest payload is missing"
    if payload.get("manifest_sha256") != digest(manifest):
        return False, "proof package manifest digest mismatch"
    for field in ("proof_profile", "authorization_id", "intent_id", "agent_id"):
        if payload.get(field) != manifest_payload.get(field):
            return False, f"proof package {field} mismatch"
    if payload.get("graph_root_digest") != manifest_payload.get("root_digest"):
        return False, "proof package graph root mismatch"
    nodes = manifest_payload.get("nodes")
    edges = manifest_payload.get("edges")
    inventory = payload.get("node_inventory")
    if not isinstance(nodes, list) or not isinstance(edges, list) or not isinstance(inventory, list):
        return False, "proof package graph inventory is missing"
    expected_inventory = [
        {"type": n.get("type"), "id": n.get("id"), "sha256": n.get("sha256")}
        for n in nodes
    ]
    if inventory != expected_inventory:
        return False, "proof package node inventory mismatch"
    if payload.get("node_count") != len(nodes) or payload.get("edge_count") != len(edges):
        return False, "proof package graph counts mismatch"
    return True, "valid proof package envelope"


def verify_proof_package(
    package: dict[str, Any] | bytes | str,
    *,
    trusted_public_key_b64: str | None = None,
) -> dict[str, Any]:
    """Verify a package entirely from its embedded bytes/data."""
    try:
        if isinstance(package, (bytes, str)):
            package = parse_proof_package(package)
        valid, reason = _validate_package_envelope(package)
        if not valid:
            return {"valid": False, "reason": reason}
        manifest = package["package"]["manifest"]
        result = verify_proof(manifest, trusted_public_key_b64=trusted_public_key_b64)
        result = dict(result)
        result["package_valid"] = True
        result["package_sha256"] = package["package_sha256"]
        return result
    except (TypeError, ValueError, KeyError) as exc:
        return {"valid": False, "reason": str(exc), "package_valid": False}


__all__ = [
    "PACKAGE_VERSION",
    "PACKAGE_MEDIA_TYPE",
    "PACKAGE_PROTOCOL",
    "build_proof_package",
    "serialize_proof_package",
    "parse_proof_package",
    "verify_proof_package",
]
