"""Execution enforcement boundary shared by local and external adapters."""
from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable


_PERMIT_ISSUER = object()


class ExecutionPermit:
    """One-shot proof that the router consumed this exact authorization."""

    __slots__ = ("authorization_id", "nonce", "_used")

    def __init__(self, authorization_id: str, nonce: str, *, _issuer: object = None):
        if _issuer is not _PERMIT_ISSUER:
            raise TypeError("execution permits can only be issued by ExecutionRouter")
        self.authorization_id = authorization_id
        self.nonce = nonce
        self._used = False

    def claim(self, authorization: dict[str, Any]) -> None:
        payload = authorization.get("payload", {})
        if (
            payload.get("authorization_id") != self.authorization_id
            or payload.get("nonce") != self.nonce
        ):
            raise PermissionError("execution permit does not match authorization")
        if self._used:
            raise PermissionError("execution permit already used")
        self._used = True


def _issue_execution_permit(authorization: dict[str, Any]) -> ExecutionPermit:
    payload = authorization["payload"]
    return ExecutionPermit(
        payload["authorization_id"], payload["nonce"], _issuer=_PERMIT_ISSUER
    )


@runtime_checkable
class ExecutionAdapter(Protocol):
    """Adapter contract for consuming Verigate execution capabilities.

    ExecutionRouter owns persistent one-time nonce consumption. It then issues
    an unforgeable-by-public-constructor, one-shot ExecutionPermit. Adapters
    must claim that permit before any post-consumption side effect.

    ``execution_external_state_scope`` is required to opt into policy-bound
    external-state execution. ``atomic`` means the adapter contract claims the
    state precondition and side effect are enforced as one backend-level
    operation. Verigate cannot independently sandbox arbitrary code behind a
    generic adapter, so the claim remains an explicit trusted-adapter boundary.
    """

    execution_external_state_scope: str

    def validate(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        """Validate adapter-specific execution prerequisites without consuming."""
        ...

    def consume(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        """Consume one-time authorization for direct adapter use."""
        ...

    def execute(
        self,
        authorization: dict[str, Any],
        side_effect: Callable[[dict[str, Any]], Any],
    ) -> Any:
        ...

    def execute_bound(
        self,
        authorization: dict[str, Any],
        external_state: dict[str, Any],
        side_effect: Callable[[dict[str, Any]], Any],
    ) -> Any:
        ...

    def execute_after_consume(
        self,
        authorization: dict[str, Any],
        side_effect: Callable[[dict[str, Any]], Any],
        *,
        permit: ExecutionPermit,
    ) -> Any:
        """Execute after router consumption with a one-shot router permit."""
        ...

    def execute_bound_after_consume(
        self,
        authorization: dict[str, Any],
        external_state: dict[str, Any],
        side_effect: Callable[[dict[str, Any]], Any],
        *,
        permit: ExecutionPermit,
    ) -> Any:
        """Execute atomically after router consumption with a one-shot permit."""
        ...

