"""Tool-call execution boundary for autonomous-agent actions."""
from __future__ import annotations

from typing import Any, Callable
import hashlib
import marshal
from types import MappingProxyType

def tool_handler_fingerprint(handler: Callable[..., Any]) -> str:
    """Stable identity for the registered executable handler.

    Bind a plain Python function's code and default arguments. Bound methods
    are rejected because their instance state is not represented by this
    fingerprint. Closure cells and mutable globals are not sandboxed; handlers
    remain trusted in-process capabilities and must not use mutable closure
    state as an authorization boundary.
    """
    if not callable(handler):
        raise ValueError("tool handler must be callable")
    if getattr(handler, "__self__", None) is not None:
        raise ValueError("bound tool methods are not supported; register a plain function")
    code = getattr(handler, "__code__", None)
    if code is None:
        raise ValueError(
            "tool handler must be a Python function or bound method with inspectable code"
        )
    defaults = getattr(handler, "__defaults__", None)
    kwdefaults = getattr(handler, "__kwdefaults__", None)
    payload = {
        "module": getattr(handler, "__module__", ""),
        "qualname": getattr(handler, "__qualname__", ""),
        # marshal serializes nested code constants recursively without repr()
        # memory addresses, so equivalent code has a stable process-independent
        # fingerprint within the supported Python runtime.
        "code_marshaled": marshal.dumps(code).hex(),
        "defaults": repr(defaults),
        "kwdefaults": repr(kwdefaults),
    }
    raw = repr(sorted(payload.items())).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def build_tool_execution_graph(tool: str, handler: Callable[..., Any]) -> dict[str, str]:
    """Build the signed, runtime-verifiable direct execution graph for one tool."""
    if not isinstance(tool, str) or not tool:
        raise ValueError("tool name must be a non-empty string")
    return {
        "module": __name__,
        "hook": "ToolExecutionAdapter",
        "router": "ExecutionRouter",
        "target": tool,
        "enforcement_scope": "direct",
        "handler_sha256": tool_handler_fingerprint(handler),
    }


# Backward-compatible private alias for existing internal callers.
_handler_fingerprint = tool_handler_fingerprint

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.storage import Storage
from enforcement.local import ExecutionGate

class ToolExecutionAdapter(ExecutionGate):
    """Execute an MCP-style tool call only from signed action data.

    The adapter enforces the direct execution boundary. A handler may not
    advertise transitive side-effect confinement unless a future adapter
    explicitly implements that stronger contract.
    """

    execution_enforcement_scope = "direct"

    def __init__(
        self,
        storage: Storage,
        public_key: Ed25519PublicKey,
        handlers: dict[str, Callable[[dict[str, Any]], Any]],
    ):
        super().__init__(storage, public_key)
        # Freeze the registry and expose it through a read-only property.
        # This prevents both item mutation and ordinary attribute replacement.
        self._handlers = MappingProxyType(dict(handlers))

    @property
    def handlers(self) -> MappingProxyType:
        """Read-only view of the registered tool handlers."""
        return self._handlers

    @staticmethod
    def _tool_name(authorization: dict[str, Any]) -> str:
        action = authorization["payload"]["action"]
        if action.get("action_type") != "mcp.tool.call":
            raise ValueError("tool adapter requires action_type=mcp.tool.call")
        target = action.get("target")
        if not isinstance(target, str) or not target:
            raise ValueError("tool action has no target")
        return target

    def validate(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        try:
            tool = self._tool_name(authorization)
        except (KeyError, TypeError, ValueError) as exc:
            return False, str(exc)
        handler = self.handlers.get(tool)
        if handler is None:
            return False, f"tool is not registered: {tool}"
        action = authorization["payload"]["action"]
        metadata = action.get("metadata")
        graph = metadata.get("execution_graph") if isinstance(metadata, dict) else None
        if not isinstance(graph, dict):
            return False, "signed execution graph with handler fingerprint is required"
        if graph.get("enforcement_scope", "direct") == "transitive":
            return False, "transitive enforcement is not supported by the direct-only tool adapter"
        try:
            expected_graph = build_tool_execution_graph(tool, handler)
        except (TypeError, ValueError) as exc:
            return False, str(exc)
        if graph != expected_graph:
            return False, "signed execution graph or execution handler drift"
        return super().validate(authorization)

    def execution_graph_binding(self, authorization: dict[str, Any]) -> dict[str, str]:
        """Expose the selected handler identity to ExecutionRouter path checks."""
        tool = self._tool_name(authorization)
        handler = self.handlers.get(tool)
        if handler is None:
            raise ValueError(f"tool is not registered: {tool}")
        return {"handler_sha256": tool_handler_fingerprint(handler)}

    def consume(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        ok, reason = self.validate(authorization)
        if not ok:
            return False, reason
        return super().consume(authorization)

    def execute_registered(self, authorization: dict[str, Any]) -> Any:
        tool = self._tool_name(authorization)
        handler = self.handlers.get(tool)
        if handler is None:
            raise PermissionError(f"tool is not registered: {tool}")
        return self.execute(authorization, handler)
