import json
import os
import signal
import sys
import tempfile
from pathlib import Path

if getattr(sys, "frozen", False):
    _BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    _SOURCE_REPO_ROOT = _BUNDLE_ROOT
    _DEFAULT_DATA_DIR = Path(sys.executable).resolve().parent / ".data"
else:
    _SOURCE_REPO_ROOT = Path(__file__).resolve().parents[3]
    _BUNDLE_ROOT = _SOURCE_REPO_ROOT
    _DEFAULT_DATA_DIR = Path(__file__).resolve().parent / ".data"

sys.path.insert(0, str(_SOURCE_REPO_ROOT))

VERSION = "0.1.3"
_POLICY_PATH = _BUNDLE_ROOT / "policies" / "default.yaml"

# Anna Executa protocol 1.1: `describe` must answer from a bare process start,
# so everything that touches the filesystem or heavy imports is lazy (see
# _get_state) and `parameters` is a LIST of parameter objects, not a JSON Schema.
MANIFEST = {
    "name": "verigate-authority",
    "display_name": "Verigate Authority",
    "version": VERSION,
    "description": (
        "Wraps Verigate's Agent Authority Control Plane as a single verigate_check tool: "
        "give it an agent action, get back a signed ALLOW/WARN/BLOCK authority decision "
        "that can be verified independently without trusting this Executa."
    ),
    "author": "rudimentall1",
    "homepage": "https://github.com/rudimentall1/verigate",
    "icon": "\U0001f6e1\ufe0f",
    "category": "security",
    "license": "MIT",
    "tools": [
        {
            "name": "verigate_check",
            "description": (
                "Ask Verigate's Agent Authority Control Plane whether an agent has authority "
                "for a payment-shaped action. Returns the signed ALLOW/WARN/BLOCK decision; "
                "the signature can be verified independently later."
            ),
            "timeout": 30,
            "parameters": [
                {"name": "agent_id", "type": "string", "description": "Identifier of the agent requesting the action.", "required": True},
                {"name": "payee", "type": "string", "description": "Recipient of the payment or action.", "required": True},
                {"name": "asset", "type": "string", "description": "Asset being moved, e.g. USDC.", "required": True},
                {"name": "network", "type": "string", "description": "Network the action runs on, e.g. base.", "required": True},
                {"name": "amount", "type": "number", "description": "Amount of the asset.", "required": True},
                {"name": "resource", "type": "string", "description": "Optional resource the action pays for.", "required": False, "default": ""},
            ],
        }
    ],
}

_REQUIRED_ARGS = [
    p["name"] for p in MANIFEST["tools"][0]["parameters"] if p["required"]
]


class RpcError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _resolve_data_dir() -> Path:
    """First writable location wins, so a read-only install dir cannot break us."""
    candidates = []
    override = os.environ.get("VERIGATE_ANNA_DATA_DIR")
    if override:
        candidates.append(Path(override))
    candidates.append(_DEFAULT_DATA_DIR)
    candidates.append(Path.home() / ".verigate-authority")
    candidates.append(Path(tempfile.gettempdir()) / "verigate-authority")
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return candidate
        except OSError:
            continue
    raise RuntimeError("no writable data directory available")


_state = None


def _get_state():
    global _state
    if _state is None:
        from attest.keys import generate_keypair, load_private_key
        from core.engine import GuardrailEngine
        from core.policy import Policy
        from core.storage import Storage

        data_dir = _resolve_data_dir()
        private_path = data_dir / "issuer.key"
        public_path = data_dir / "issuer.pub"
        if not private_path.exists():
            generate_keypair(private_path, public_path)
        engine = GuardrailEngine(
            Policy.load(str(_POLICY_PATH)), Storage(str(data_dir / "verigate.db"))
        )
        _state = (engine, load_private_key(private_path))
    return _state


def _verigate_check(args: dict) -> dict:
    for name in _REQUIRED_ARGS:
        if name not in args:
            raise RpcError(-32602, f"missing required argument: {name}")
    try:
        from core.models import PaymentIntent

        intent = PaymentIntent(
            agent_id=args["agent_id"],
            payee=args["payee"],
            asset=args["asset"],
            network=args["network"],
            amount=float(args["amount"]),
            resource=args.get("resource", ""),
        )
        engine, private_key = _get_state()
        attestation = engine.authorize(intent, private_key)
    except (ValueError, TypeError) as exc:
        return {"success": False, "error": f"invalid arguments: {exc}"}
    return {"success": True, "data": attestation}


def invoke(tool: str, args: dict) -> dict:
    if tool != "verigate_check":
        raise RpcError(-32601, f"Unknown tool: {tool}")
    if not isinstance(args, dict):
        raise RpcError(-32602, "arguments must be an object")
    return _verigate_check(args)


def handle(request: dict):
    method = request.get("method")
    params = request.get("params") or {}
    if method == "describe":
        return MANIFEST
    if method == "health":
        return {"status": "ready", "message": "", "details": {}}
    if method == "invoke":
        if not isinstance(params, dict) or "tool" not in params:
            raise RpcError(-32602, "invoke requires params.tool")
        return invoke(params["tool"], params.get("arguments") or {})
    raise RpcError(-32601, f"Unknown method: {method}")


def _write(frame: dict) -> None:
    sys.stdout.write(json.dumps(frame) + "\n")
    sys.stdout.flush()


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    except (AttributeError, ValueError):
        pass
    try:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    except (ValueError, OSError):
        pass

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            _write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        if not isinstance(request, dict):
            _write({"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}})
            continue
        request_id = request.get("id")
        try:
            result = handle(request)
            _write({"jsonrpc": "2.0", "id": request_id, "result": result})
        except RpcError as exc:
            _write({"jsonrpc": "2.0", "id": request_id, "error": {"code": exc.code, "message": exc.message}})
        except Exception as exc:  # noqa: BLE001 - never let one request kill the process
            _write({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": f"Internal error: {exc}"}})


if __name__ == "__main__":
    main()