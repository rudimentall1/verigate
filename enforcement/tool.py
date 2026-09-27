"""Tool-call execution boundary for autonomous-agent actions."""
from __future__ import annotations

from typing import Any, Callable
import hashlib

def _handler_fingerprint(handler: Callable[..., Any]) -> str:
    """Stable identity for the registered executable handler.

    Bind the code object plus callable configuration that can change behavior
    without replacing the function object itself. This deliberately does not
    claim to sandbox arbitrary globals or child side effects inside a trusted
    handler.
    """
    code = getattr(handler, "__code__", None)
    defaults = getattr(handler, "__defaults__", None)
    kwdefaults = getattr(handler, "__kwdefaults__", None)
    payload = {
        "module": getattr(handler, "__module__", ""),
        "qualname": getattr(handler, "__qualname__", ""),
        "code": getattr(code, "co_code", b"").hex(),
        "consts": repr(getattr(code, "co_consts", ())),
        "names": tuple(getattr(code, "co_names", ())),
        "varnames": tuple(getattr(code, "co_varnames", ())),
        "freevars": tuple(getattr(code, "co_freevars", ())),
        "defaults": repr(defaults),
        "kwdefaults": repr(kwdefaults),
    }
    raw = repr(sorted(payload.items())).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

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
        self.handlers = dict(handlers)

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
        if isinstance(graph, dict) and graph.get("handler_sha256"):
            actual = _handler_fingerprint(handler)
            if graph["handler_sha256"] != actual:
                return False, "execution handler drift"
        return super().validate(authorization)

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
