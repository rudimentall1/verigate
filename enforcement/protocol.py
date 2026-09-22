"""Execution enforcement boundary shared by local and external adapters."""
from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class ExecutionAdapter(Protocol):
    """Adapter contract for consuming Verigate execution capabilities.

    Adapters must fail closed: the supplied side effect may run only after
    the adapter has accepted the one-time ExecutionAuthorization.
    """

    def consume(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        ...

    def execute(self, authorization: dict[str, Any], side_effect: Callable[[], Any]) -> Any:
        ...
