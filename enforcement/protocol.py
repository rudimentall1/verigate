"""Execution enforcement boundary shared by local and external adapters."""
from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class ExecutionAdapter(Protocol):
    """Adapter contract for consuming Verigate execution capabilities.

    Adapters must own one-time nonce consumption inside ``execute`` or
    ``execute_bound``. The router calls only these self-consuming methods;
    post-consumption implementation hooks remain private to each adapter.

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
        """Execute while enforcing the supplied state precondition atomically."""
        ...

