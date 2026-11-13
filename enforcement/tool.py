"""Tool-call execution boundary for autonomous-agent actions."""
from __future__ import annotations

from typing import Any, Callable
import copy
import hashlib
import inspect
import marshal
from types import MappingProxyType

def handler_fingerprint(handler: Callable[..., Any]) -> str:
    """Stable identity for the registered executable handler.

    Bind a Python function's serialized code object and declared defaults.
    Callable instances are rejected because hashing their type name alone
    would not bind the implementation of __call__. Globals and mutable
    closure state remain trusted runtime dependencies; this is an identity
    check, not a sandbox or a transitive side-effect proof.
    """
    if not inspect.isfunction(handler):
        raise TypeError("tool handlers must be plain Python functions")
    code = getattr(handler, "__code__", None)
    defaults = getattr(handler, "__defaults__", None)
    kwdefaults = getattr(handler, "__kwdefaults__", None)
    payload = {
        "module": getattr(handler, "__module__", ""),
        "qualname": getattr(handler, "__qualname__", ""),
        "code": marshal.dumps(code).hex() if code is not None else "",
        "names": tuple(getattr(code, "co_names", ())),
        "varnames": tuple(getattr(code, "co_varnames", ())),
        "freevars": tuple(getattr(code, "co_freevars", ())),
        "defaults": repr(defaults),
        "kwdefaults": repr(kwdefaults),
    }
    raw = repr(sorted(payload.items())).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


# Backward-compatible private alias for existing integrations.
_handler_fingerprint = handler_fingerprint

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.execution_graph import verify_execution_graph
from core.storage import Storage
from enforcement.local import ExecutionGate

class ToolExecutionAdapter(ExecutionGate):
    """Execute an MCP-style tool call only from signed action data.

    The adapter enforces the direct execution boundary. Before signing an
    action, callers must bind the exact registered Python function with
    ``metadata["execution_graph"]["handler_sha256"] = handler_fingerprint(fn)``.
    The graph must also identify this adapter, router, target, and direct
    enforcement scope. A handler may not advertise transitive side-effect
    confinement unless a future adapter explicitly implements that contract.
    """

    execution_enforcement_scope = "direct"

    def __init__(
        self,
        storage: Storage,
        public_key: Ed25519PublicKey,
        handlers: dict[str, Callable[[dict[str, Any]], Any]],
    ):
        super().__init__(storage, public_key)
        # Freeze the registry so validation and invocation cannot observe
        # different handlers due to an in-process mapping mutation.
        self.handlers = MappingProxyType(dict(handlers))

    @staticmethod
    def _tool_name(authorization: dict[str, Any]) -> str:
        action = authorization["payload"]["action"]
        if action.get("action_type") != "mcp.tool.call":
            raise ValueError("tool adapter requires action_type=mcp.tool.call")
        target = action.get("target")
        if not isinstance(target, str) or not target:
            raise ValueError("tool action has no target")
        return target

    def execution_graph_identity(self, action: dict[str, Any]) -> dict[str, Any]:
        """Expose the registered handler identity to ExecutionRouter."""
        target = action.get("target") if isinstance(action, dict) else None
        handler = self.handlers.get(target) if isinstance(target, str) else None
        if handler is None:
            return {}
        try:
            return {"handler_sha256": handler_fingerprint(handler)}
        except (TypeError, ValueError):
            return {}

    def validate(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        authorization = copy.deepcopy(authorization)
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
            return False, "signed execution graph is required"
        expected = graph.get("handler_sha256")
        if not isinstance(expected, str) or len(expected) != 64:
            return False, "signed handler fingerprint is required"
        try:
            int(expected, 16)
        except ValueError:
            return False, "signed handler fingerprint is malformed"
        try:
            actual = _handler_fingerprint(handler)
        except (TypeError, ValueError):
            return False, "registered tool handler has an unsupported callable type"
        if expected.lower() != actual:
            return False, "execution handler drift"
        actual_graph = {
            "module": self.__class__.__module__,
            "hook": self.__class__.__name__,
            "router": "ExecutionRouter",
            "target": tool,
            "enforcement_scope": self.execution_enforcement_scope,
            "handler_sha256": actual,
        }
        graph_ok, graph_reason = verify_execution_graph(graph, actual_graph)
        if not graph_ok:
            return False, graph_reason
        return super().validate(authorization)

    def consume(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        ok, reason = self.validate(authorization)
        if not ok:
            return False, reason
        return super().consume(authorization)

    def execute_registered(self, authorization: dict[str, Any]) -> Any:
        # Resolve the handler and execute against one adapter-owned snapshot.
        authorization = copy.deepcopy(authorization)
        tool = self._tool_name(authorization)
        handler = self.handlers.get(tool)
        if handler is None:
            raise PermissionError(f"tool is not registered: {tool}")
        return self.execute(authorization, handler)
