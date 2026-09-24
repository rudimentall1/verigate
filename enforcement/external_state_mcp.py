"""Live MCP resource-state verification before tool execution."""
from __future__ import annotations

from typing import Any, Callable

from core.external_state import external_state_digest_from_observation


class MCPExternalStateVerifier:
    """Verify read-only MCP state immediately before a tool side effect.

    The provider must return a canonical JSON-compatible observation. Verigate
    hashes that observation and compares it with the authorization binding.
    The provider is intentionally injected so transports can be MCP SDK,
    stdio, HTTP, or an enterprise gateway without coupling the core to one SDK.
    """

    def __init__(self, provider: Callable[[str, str, dict[str, Any]], dict[str, Any]]):
        self.provider = provider

    def __call__(self, binding: dict[str, Any], action: dict[str, Any]) -> tuple[bool, str]:
        try:
            if binding.get("kind") != "mcp.state":
                return False, "unsupported MCP state binding kind"
            tool = binding.get("tool")
            reference = binding.get("reference")
            if not isinstance(tool, str) or not tool.strip():
                return False, "MCP state binding has no tool"
            if not isinstance(reference, str) or not reference.strip():
                return False, "MCP state binding has no reference"
            if action.get("action_type") != "mcp.tool.call":
                return False, "MCP state verifier requires mcp.tool.call"
            if action.get("target") != tool:
                return False, "MCP state tool does not match authorized target"
            observation = self.provider(tool, reference, binding)
            if not isinstance(observation, dict):
                return False, "MCP state provider returned invalid observation"
            normalized = {str(k): observation[k] for k in sorted(observation)}
            if external_state_digest_from_observation(normalized) != binding.get("digest"):
                return False, "MCP external state digest changed"
            return True, "MCP state matches authorization"
        except Exception as exc:
            return False, f"MCP state verification failed: {exc}"
