"""Execution enforcement boundary shared by local and external adapters."""
from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class ExecutionAdapter(Protocol):
    """Adapter contract for consuming Verigate execution capabilities.

    Adapters must fail closed: the supplied side effect may run only after
    the adapter has accepted the one-time ExecutionAuthorization.
    """

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

    def execute_after_consume(
        self,
        authorization: dict[str, Any],
        side_effect: Callable[[dict[str, Any]], Any],
    ) -> Any:
        """Execute only after the router has consumed the authorization."""
        ...

    def execute_bound(
        self,
        authorization: dict[str, Any],
        external_state: dict[str, Any],
        side_effect: Callable[[dict[str, Any]], Any],
    ) -> Any:
        """Execute while enforcing the supplied state precondition atomically."""
        ...

    def execute_bound_after_consume(
        self,
        authorization: dict[str, Any],
        external_state: dict[str, Any],
        side_effect: Callable[[dict[str, Any]], Any],
    ) -> Any:
        """Execute an atomic-state action after router-side consumption."""
        ...
