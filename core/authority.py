"""Authority graph and cryptographically verified capability delegation."""
from __future__ import annotations

import base64
import json
import uuid
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .capabilities import CapabilityRegistry
from .models import AgentIdentity, Capability
from .storage import Storage


_MAX_DELEGATION_DEPTH = 32


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _capability_payload(capability: Capability) -> dict[str, Any]:
    return {
        "capability_id": capability.capability_id,
        "agent_id": capability.agent_id,
        "identity_id": capability.identity_id,
        "delegated_from": capability.delegated_from,
        "delegated_by_identity_id": capability.delegated_by_identity_id,
        "delegation_depth": capability.delegation_depth,
        "allowed_actions": capability.allowed_actions,
        "allowed_purposes": capability.allowed_purposes,
        "context_constraints": capability.context_constraints,
        "allowed_targets": capability.allowed_targets,
        "allowed_resources": capability.allowed_resources,
        "allowed_networks": capability.allowed_networks,
        "allowed_assets": capability.allowed_assets,
        "max_per_action": capability.max_per_action,
        "aggregate_limits": capability.aggregate_limits,
        "conditions": capability.conditions,
        "version": capability.version,
        "issued_at": capability.issued_at,
        "expires_at": capability.expires_at,
        "metadata": capability.metadata,
    }


def sign_delegation(
    parent_capability_id: str,
    child_capability: Capability,
    delegator_identity_id: str,
    private_key: Ed25519PrivateKey,
) -> str:
    payload = {
        "delegation_version": 1,
        "parent_capability_id": parent_capability_id,
        "delegator_identity_id": delegator_identity_id,
        "child_capability": _capability_payload(child_capability),
        "child_capability_sha256": child_capability.digest,
    }
    return base64.b64encode(private_key.sign(_canonical(payload))).decode("ascii")


def verify_delegation(
    parent_capability_id: str,
    child_capability: Capability,
    delegator_identity_id: str,
    signature: str,
    identity: AgentIdentity,
) -> tuple[bool, str]:
    try:
        if identity.key_id != delegator_identity_id:
            return False, "delegator identity mismatch"
        raw = base64.b64decode(identity.public_key_b64, validate=True)
        if len(raw) != 32:
            return False, "invalid delegator public key"
        payload = {
            "delegation_version": 1,
            "parent_capability_id": parent_capability_id,
            "delegator_identity_id": delegator_identity_id,
            "child_capability": _capability_payload(child_capability),
            "child_capability_sha256": child_capability.digest,
        }
        Ed25519PublicKey.from_public_bytes(raw).verify(
            base64.b64decode(signature, validate=True),
            _canonical(payload),
        )
        return True, "valid capability delegation"
    except (ValueError, InvalidSignature):
        return False, "invalid or tampered capability delegation"


def _is_subset(child: tuple[str, ...], parent: tuple[str, ...]) -> bool:
    if not parent:
        return True
    return bool(child) and set(child).issubset(parent)


def _limits_subset(
    child: dict[str, float],
    parent: dict[str, float],
) -> bool:
    for key, child_limit in child.items():
        parent_limit = parent.get(key)
        if parent_limit is not None and child_limit > parent_limit:
            return False
    if not parent:
        return True
    return all(key in child for key in parent)


def validate_delegation_scope(
    parent: Capability,
    child: Capability,
) -> tuple[bool, str]:
    if child.delegated_from != parent.capability_id:
        return False, "delegated_from does not match parent capability"
    if child.delegation_depth != parent.delegation_depth + 1:
        return False, "invalid delegation depth"
    if child.delegation_depth > _MAX_DELEGATION_DEPTH:
        return False, "delegation depth exceeds maximum"
    if parent.identity_id is None:
        return False, "parent capability is not identity-bound"
    if child.delegated_by_identity_id != parent.identity_id:
        return False, "delegator identity does not own parent capability"

    for field_name in (
        "allowed_actions",
        "allowed_purposes",
        "allowed_targets",
        "allowed_resources",
        "allowed_networks",
        "allowed_assets",
    ):
        if not _is_subset(
            getattr(child, field_name),
            getattr(parent, field_name),
        ):
            return False, f"delegated {field_name} exceeds parent scope"

    for key, parent_expected in parent.context_constraints.items():
        if key not in child.context_constraints:
            return False, f"delegated context constraint '{key}' was removed"
        child_expected = child.context_constraints[key]
        if isinstance(parent_expected, (list, tuple, set)):
            if isinstance(child_expected, (list, tuple, set)):
                if not set(child_expected).issubset(set(parent_expected)):
                    return False, f"delegated context constraint '{key}' exceeds parent scope"
            elif child_expected not in parent_expected:
                return False, f"delegated context constraint '{key}' exceeds parent scope"
        elif child_expected != parent_expected:
            return False, f"delegated context constraint '{key}' exceeds parent scope"

    if not _limits_subset(child.max_per_action, parent.max_per_action):
        return False, "delegated per-action limits exceed parent authority"
    if not _limits_subset(child.aggregate_limits, parent.aggregate_limits):
        return False, "delegated aggregate limits exceed parent authority"

    if not set(parent.conditions).issubset(child.conditions):
        return False, "delegation removed a parent condition"

    if parent.expires_at is not None:
        if child.expires_at is None or child.expires_at > parent.expires_at:
            return False, "delegated capability outlives parent capability"

    return True, "delegation scope valid"


class AuthorityGraph:
    """Queryable authority graph built from durable identity/capability edges."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def outgoing(self, node_type: str, node_id: str) -> list[dict]:
        return self.storage.authority_edges(
            source_type=node_type,
            source_id=node_id,
        )

    def incoming(self, node_type: str, node_id: str) -> list[dict]:
        return self.storage.authority_edges(
            target_type=node_type,
            target_id=node_id,
        )

    def authority_path(self, capability_id: str) -> list[dict]:
        """Return the capability delegation chain from root to leaf."""
        path: list[dict] = []
        current = self.storage.capability(capability_id)
        visited: set[str] = set()

        while current is not None:
            if current.capability_id in visited:
                raise RuntimeError("authority graph cycle detected")
            visited.add(current.capability_id)
            path.append({
                "type": "capability",
                "id": current.capability_id,
                "agent_id": current.agent_id,
                "identity_id": current.identity_id,
                "version": current.version,
                "digest": current.digest,
                "delegated_from": current.delegated_from,
                "delegation_depth": current.delegation_depth,
            })
            if current.delegated_from is None:
                break
            current = self.storage.capability(current.delegated_from)

        path.reverse()
        return path

    def explain(self, capability_id: str) -> dict[str, Any]:
        capability = self.storage.capability(capability_id)
        if capability is None:
            raise LookupError("capability not found")
        return {
            "capability": _capability_payload(capability),
            "path": self.authority_path(capability_id),
            "outgoing_edges": self.outgoing("capability", capability_id),
            "incoming_edges": self.incoming("capability", capability_id),
        }


class CapabilityDelegationService:
    """Create delegated capabilities only inside the parent's authority scope."""

    def __init__(self, storage: Storage):
        self.storage = storage
        self.capabilities = CapabilityRegistry(storage)

    def delegate(
        self,
        parent_capability_id: str,
        child_capability: Capability,
        delegator_identity_id: str,
        delegation_signature: str,
    ) -> dict[str, Any]:
        parent = self.capabilities.resolve(parent_capability_id)
        identity = self.storage.identity(delegator_identity_id)
        if identity is None:
            raise LookupError("delegator identity not found")
        if not self.storage.identity_is_active(delegator_identity_id):
            raise PermissionError("delegator identity is not active")
        if parent.identity_id != delegator_identity_id:
            raise PermissionError("delegator does not own parent capability")
        if child_capability.identity_id is None:
            raise ValueError("delegated capability must bind a recipient identity")

        recipient = self.storage.identity(child_capability.identity_id)
        if recipient is None:
            raise LookupError("recipient identity not found")
        if not self.storage.identity_is_active(child_capability.identity_id):
            raise PermissionError("recipient identity is not active")
        if recipient.agent_id != child_capability.agent_id:
            raise PermissionError("recipient identity does not match child agent")

        valid_scope, reason = validate_delegation_scope(parent, child_capability)
        if not valid_scope:
            raise PermissionError(reason)

        valid_signature, reason = verify_delegation(
            parent_capability_id,
            child_capability,
            delegator_identity_id,
            delegation_signature,
            identity,
        )
        if not valid_signature:
            raise PermissionError(reason)

        edge_id = self.storage.register_delegated_capability(
            child_capability,
            parent_capability_id,
            delegator_identity_id=delegator_identity_id,
            delegation_signature=delegation_signature,
        )
        return {
            "capability": child_capability,
            "parent_capability_id": parent_capability_id,
            "delegator_identity_id": delegator_identity_id,
            "edge_id": edge_id,
            "authority_path": AuthorityGraph(self.storage).authority_path(
                child_capability.capability_id
            ),
        }

    def revoke(self, child_capability_id: str) -> bool:
        capability = self.storage.capability(child_capability_id)
        if capability is None:
            return False
        revoked = self.storage.revoke_capability(child_capability_id)
        if capability.delegated_from:
            for edge in self.storage.authority_edges(
                source_type="capability",
                source_id=capability.delegated_from,
                target_type="capability",
                target_id=child_capability_id,
                active_only=True,
            ):
                self.storage.revoke_authority_edge(edge["edge_id"])
        return revoked
