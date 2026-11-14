"""Tool-call execution boundary for autonomous-agent actions."""
from __future__ import annotations

from typing import Any, Callable
import hashlib
import marshal
from types import MappingProxyType

def _stable_default_value(value: Any) -> str:
    """Serialize only immutable, deterministic default values."""
    value_type = type(value)
    if value is None:
        return "none"
    if value_type is bool:
        return "bool:true" if value else "bool:false"
    if value_type is int:
        return f"int:{value}"
    if value_type is str:
        return f"str:{value!r}"
    if value_type is bytes:
        return f"bytes:{value.hex()}"
    if value_type is float:
        import math
        if not math.isfinite(value):
            raise ValueError("handler defaults must not contain non-finite floats")
        return f"float:{value.hex()}"
    if value_type is tuple:
        return "tuple:[" + ",".join(_stable_default_value(item) for item in value) + "]"
    if value_type is frozenset:
        items = sorted(_stable_default_value(item) for item in value)
        return "frozenset:[" + ",".join(items) + "]"
    raise ValueError(
        "handler defaults must use immutable deterministic primitives; "
        f"unsupported default type: {value_type.__name__}"
    )


def _stable_handler_defaults(handler: Callable[..., Any]) -> tuple[str, str]:
    defaults = getattr(handler, "__defaults__", None)
    kwdefaults = getattr(handler, "__kwdefaults__", None)
    positional = (
        "none" if defaults is None
        else _stable_default_value(defaults)
    )
    if kwdefaults is None:
        keyword = "none"
    elif type(kwdefaults) is dict and all(type(key) is str for key in kwdefaults):
        keyword = "dict:{" + ",".join(
            f"{key!r}:{_stable_default_value(kwdefaults[key])}"
            for key in sorted(kwdefaults)
        ) + "}"
    else:
        raise ValueError("handler keyword defaults must be a plain string-keyed dict")
    return positional, keyword


def _stable_handler_closure(handler: Callable[..., Any]) -> str:
    """Bind closure cells only when every captured value is immutable and deterministic."""
    code = getattr(handler, "__code__", None)
    closure = getattr(handler, "__closure__", None)
    if code is None or closure is None:
        return "none"
    if len(code.co_freevars) != len(closure):
        raise ValueError("handler closure metadata is inconsistent")
    captured = []
    for name, cell in zip(code.co_freevars, closure):
        try:
            value = cell.cell_contents
        except ValueError as exc:
            raise ValueError("handler closure contains an empty cell") from exc
        try:
            encoded = _stable_default_value(value)
        except ValueError as exc:
            raise ValueError(
                f"handler closure variable {name!r} must be immutable and deterministic"
            ) from exc
        captured.append((name, encoded))
    return repr(captured)


def tool_handler_fingerprint(handler: Callable[..., Any]) -> str:
    """Stable identity for the registered executable handler.

    Bind code, deterministic defaults, and immutable closure values. Bound
    methods and mutable/custom closure cells are rejected. Mutable globals and
    imported dependencies remain trusted in-process capabilities; this is not
    a Python sandbox.
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
    defaults, kwdefaults = _stable_handler_defaults(handler)
    closure = _stable_handler_closure(handler)
    payload = {
        "module": getattr(handler, "__module__", ""),
        "qualname": getattr(handler, "__qualname__", ""),
        # marshal serializes nested code constants recursively without repr()
        # memory addresses, so equivalent code has a stable process-independent
        # fingerprint within the supported Python runtime.
        "code_marshaled": marshal.dumps(code).hex(),
        "defaults": defaults,
        "kwdefaults": kwdefaults,
        "closure": closure,
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

    def execute_after_consume(
        self,
        authorization: dict[str, Any],
        _side_effect: Callable[[dict[str, Any]], Any],
    ) -> Any:
        """Invoke only the registered handler after the router consumes authority.

        The router callback is deliberately ignored: accepting it as the tool
        implementation would let the caller replace the signed handler at the
        final execution boundary.
        """
        tool = self._tool_name(authorization)
        handler = self.handlers.get(tool)
        if handler is None:
            raise PermissionError(f"tool is not registered: {tool}")
        return handler(authorization["payload"]["action"])

    def execute_registered(self, authorization: dict[str, Any]) -> Any:
        # Keep the convenience API on the same validate -> consume -> dispatch
        # path as ExecutionRouter; never pass a caller-selected implementation.
        return self.execute(authorization, lambda _action: None)
