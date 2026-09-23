"""Capability registry for Verigate authority lifecycle.

The registry is the source of truth for currently active agent capabilities.
Revocation only affects future authorization; an already-issued execution
authorization remains bound to the capability version and digest embedded in
that signed artifact.
"""
from __future__ import annotations

from .models import ActionIntent, Capability
from .storage import Storage


class CapabilityRegistry:
    """Register, resolve and revoke programmable agent authority."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def register(self, capability: Capability) -> Capability:
        if capability.identity_id is not None:
            identity = self.storage.identity(capability.identity_id)
            if identity is None:
                raise LookupError("capability identity not found")
            if identity.agent_id != capability.agent_id:
                raise PermissionError("capability identity does not match agent")
        self.storage.register_capability(capability)
        return capability

    def resolve(self, capability_id: str, *, require_active: bool = True) -> Capability:
        capability = self.storage.capability(capability_id)
        if capability is None:
            raise LookupError("capability not found")
        if require_active and not self.effective_active(capability_id):
            raise PermissionError("capability is not active or has an ineffective authority chain")
        return capability

    def effective_active(self, capability_id: str, *, max_depth: int = 32) -> bool:
        """A capability is active only when its full authority chain is active."""
        visited: set[str] = set()
        current_id = capability_id
        depth = 0
        while current_id is not None:
            if current_id in visited:
                return False
            if depth > max_depth:
                return False
            visited.add(current_id)
            current = self.storage.capability(current_id)
            if current is None or not self.storage.capability_is_active(current_id):
                return False
            if current.identity_id is not None and not self.storage.identity_is_active(current.identity_id):
                return False
            current_id = current.delegated_from
            depth += 1
        return True

    def revoke(self, capability_id: str) -> bool:
        return self.storage.revoke_capability(capability_id)

    def authorize(
        self,
        capability_id: str,
        action: ActionIntent,
        identity_id: str | None = None,
    ) -> Capability:
        capability = self.resolve(capability_id)
        if capability.identity_id is not None:
            if identity_id != capability.identity_id:
                raise PermissionError("capability identity mismatch")
            if not self.storage.identity_is_active(capability.identity_id):
                raise PermissionError("capability identity is not active")
            identity = self.storage.identity(capability.identity_id)
            if identity is None or identity.agent_id != capability.agent_id:
                raise PermissionError("capability identity binding is invalid")
        permitted, reason = capability.permits(action)
        if not permitted:
            raise PermissionError(reason)
        return capability
    def active(self, capability_id: str) -> bool:
        """Return whether a capability can grant new authority now."""
        return self.effective_active(capability_id)

    def assert_authority(
        self,
        capability_id: str,
        action: ActionIntent,
        identity_id: str | None = None,
    ) -> Capability:
        """Strict control-plane gate used before execution authorization."""
        return self.authorize(capability_id, action, identity_id=identity_id)
