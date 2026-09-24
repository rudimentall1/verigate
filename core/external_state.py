"""Cryptographic binding for external state/preconditions at execution time."""
from __future__ import annotations
import hashlib
import json
from typing import Any, Protocol

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


def external_state_digest_from_observation(observation: dict[str, Any]) -> str:
    data = json.dumps(observation, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class ExternalStateVerifier(Protocol):
    """Execution-boundary contract for live external state verification."""

    def __call__(self, binding: dict[str, Any], action: dict[str, Any]) -> tuple[bool, str]: ...


class ExternalStateVerifierRegistry:
    """Deterministic registry for live external-state verifiers."""

    def __init__(self, verifiers: dict[str, ExternalStateVerifier] | None = None):
        self._verifiers = dict(verifiers or {})

    def register(self, kind: str, verifier: ExternalStateVerifier) -> None:
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("external state verifier kind must be non-empty")
        self._verifiers[kind.strip()] = verifier

    def resolve(self, kind: str) -> ExternalStateVerifier:
        verifier = self._verifiers.get(kind)
        if verifier is None:
            raise KeyError(f"no external state verifier registered for kind '{kind}'")
        return verifier

    def verify(self, binding: dict[str, Any], action: dict[str, Any]) -> tuple[bool, str]:
        kind = binding.get("kind") if isinstance(binding, dict) else None
        if not isinstance(kind, str) or not kind.strip():
            return False, "external state binding is missing kind"
        try:
            return self.resolve(kind)(binding, action)
        except KeyError as exc:
            return False, str(exc)
        except Exception as exc:
            return False, f"external state verifier failed: {exc}"


def external_state_requirement_for_action(
    requirements: list[dict[str, Any]], action: dict[str, Any]
) -> dict[str, Any] | None:
    """Resolve the most specific policy state requirement for an action."""
    if not isinstance(requirements, list):
        return None
    action_type = action.get("action_type")
    target = action.get("target")
    matches: list[tuple[int, dict[str, Any]]] = []
    for requirement in requirements:
        if not isinstance(requirement, dict):
            continue
        ra = requirement.get("action_type", "*")
        rt = requirement.get("target", "*")
        if ra not in ("*", action_type) or rt not in ("*", target):
            continue
        if not isinstance(requirement.get("kind"), str) or not requirement["kind"].strip():
            continue
        specificity = (2 if ra != "*" else 0) + (1 if rt != "*" else 0)
        matches.append((specificity, requirement))
    if not matches:
        return None
    _, selected = max(matches, key=lambda item: item[0])
    return {str(k): selected[k] for k in sorted(selected)}


def validate_external_state_requirement(requirement: dict[str, Any] | None) -> tuple[bool, str]:
    if requirement is None:
        return True, "no external state requirement"
    if not isinstance(requirement, dict):
        return False, "external state requirement must be an object"
    if not isinstance(requirement.get("kind"), str) or not requirement["kind"].strip():
        return False, "external state requirement is missing kind"
    return True, "external state requirement is valid"
