import json
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    _BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    _SOURCE_REPO_ROOT = _BUNDLE_ROOT
    _DATA_DIR = Path(sys.executable).resolve().parent / ".data"
else:
    _SOURCE_REPO_ROOT = Path(__file__).resolve().parents[3]
    _BUNDLE_ROOT = _SOURCE_REPO_ROOT
    _DATA_DIR = Path(__file__).resolve().parent / ".data"

sys.path.insert(0, str(_SOURCE_REPO_ROOT))

from attest.keys import generate_keypair, load_private_key
from core.engine import GuardrailEngine
from core.models import PaymentIntent
from core.policy import Policy
from core.storage import Storage

_PRIVATE_KEY_PATH = _DATA_DIR / "issuer.key"
_PUBLIC_KEY_PATH = _DATA_DIR / "issuer.pub"
_DB_PATH = _DATA_DIR / "verigate.db"
_POLICY_PATH = _BUNDLE_ROOT / "policies" / "default.yaml"

_DATA_DIR.mkdir(parents=True, exist_ok=True)

if not _PRIVATE_KEY_PATH.exists():
    generate_keypair(_PRIVATE_KEY_PATH, _PUBLIC_KEY_PATH)

_engine = GuardrailEngine(Policy.load(str(_POLICY_PATH)), Storage(str(_DB_PATH)))
_private_key = load_private_key(_PRIVATE_KEY_PATH)

MANIFEST = {
    "name": "tool-dev-verigate-authority",
    "version": "0.1.2",
    "tools": [
        {
            "name": "verigate_check",
            "description": "Ask Verigate's Agent Authority Control Plane whether an agent has authority for a payment-shaped action. Returns the signed ALLOW/WARN/BLOCK decision; the signature can be verified independently later without trusting this Executa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string"},
                    "payee": {"type": "string"},
                    "asset": {"type": "string"},
                    "network": {"type": "string"},
                    "amount": {"type": "number"},
                    "resource": {"type": "string", "default": ""}
                },
                "required": ["agent_id", "payee", "asset", "network", "amount"],
                "additionalProperties": False
            }
        }
    ]
}

def _verigate_check(args: dict) -> dict:
    intent = PaymentIntent(
        agent_id=args["agent_id"],
        payee=args["payee"],
        asset=args["asset"],
        network=args["network"],
        amount=float(args["amount"]),
        resource=args.get("resource", "")
    )
    attestation = _engine.authorize(intent, _private_key)
    return {"success": True, "data": attestation}

def invoke(method: str, args: dict) -> dict:
    if method == "verigate_check":
        try:
            return _verigate_check(args)
        except (KeyError, ValueError, TypeError) as exc:
            return {"success": False, "error": f"invalid arguments: {exc}"}
    return {"success": False, "error": f"unknown method: {method}"}

def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        try:
            if req.get("method") == "describe":
                result = MANIFEST
            elif req.get("method") == "health":
                result = {"status": "ready"}
            elif req.get("method") == "invoke":
                result = invoke(req["params"]["tool"], req["params"].get("arguments", {}))
            else:
                raise ValueError(f"unknown rpc: {req.get('method')}")
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req.get("id"), "result": result}) + "\n")
        except Exception as e:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req.get("id"), "error": {"code": -32601, "message": str(e)}}) + "\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
