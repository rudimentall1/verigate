"""Anna Executa for Verigate: gives Anna a way to call Verigate's existing
Agent Authority Control Plane without changing anything in the verigate
package itself. This file only imports core.* and attest.* as a library --
same classes api/main.py itself constructs -- and speaks Anna's stdio
JSON-RPC Executa protocol (describe / health / invoke) on top of that.

Verigate's own idea, unchanged: give it an agent action, it decides
authority, execution produces evidence, anyone can verify that evidence
later without trusting Verigate.
"""

import json
import os
import sys
from pathlib import Path

# This executa lives at <repo>/anna/executas/verigate-authority/. Put the
# repo root on sys.path so `import core...` / `import attest...` resolve to
# the real verigate package -- no copy, no fork, no change to those modules.
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from attest.keys import generate_keypair, load_private_key  # noqa: E402
from core.engine import GuardrailEngine  # noqa: E402
from core.models import PaymentIntent  # noqa: E402
from core.policy import Policy  # noqa: E402
from core.storage import Storage  # noqa: E402

# Self-contained: its own key and its own SQLite file, separate from
# whatever the "real" verigate deployment (api/main.py, cli.py) uses. This
# executa never touches the main deployment's keys/ or verigate.db.
_DATA_DIR = Path(__file__).resolve().parent / ".data"
_DATA_DIR.mkdir(exist_ok=True)
_PRIVATE_KEY_PATH = _DATA_DIR / "issuer.key"
_PUBLIC_KEY_PATH = _DATA_DIR / "issuer.pub"
_DB_PATH = _DATA_DIR / "verigate.db"
_POLICY_PATH = _REPO_ROOT / "policies" / "default.yaml"

if not _PRIVATE_KEY_PATH.exists():
    generate_keypair(_PRIVATE_KEY_PATH, _PUBLIC_KEY_PATH)

_engine = GuardrailEngine(Policy.load(str(_POLICY_PATH)), Storage(str(_DB_PATH)))
_private_key = load_private_key(_PRIVATE_KEY_PATH)

MANIFEST = {
    "name": "tool-dev-verigate-authority",
    "version": "0.1.0",
    "tools": [
        {
            "name": "verigate_check",
            "description": (
                "Ask Verigate's Agent Authority Control Plane whether an "
                "agent has authority for a payment-shaped action. Returns "
                "the signed ALLOW/WARN/BLOCK decision; the signature can be "
                "verified independently later without trusting this Executa."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string"},
                    "payee": {"type": "string"},
                    "asset": {"type": "string"},
                    "network": {"type": "string"},
                    "amount": {"type": "number"},
                    "resource": {"type": "string", "default": ""},
                },
                "required": ["agent_id", "payee", "asset", "network", "amount"],
                "additionalProperties": False,
            },
        },
    ],
}


def _verigate_check(args: dict) -> dict:
    intent = PaymentIntent(
        agent_id=args["agent_id"],
        payee=args["payee"],
        asset=args["asset"],
        network=args["network"],
        amount=float(args["amount"]),
        resource=args.get("resource", ""),
    )
    attestation = _engine.authorize(intent, _private_key)
    return {"success": True, "data": attestation}


def invoke(method: str, args: dict) -> dict:
    # Tool methods MUST return the dispatcher contract envelope:
    #   {"success": True,  "data":  <payload-dict>}
    #   {"success": False, "error": "<reason>"}
    # Anything else surfaces to the iframe as `tool_failed`.
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
        except Exception as e:  # noqa: BLE001
            sys.stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": req.get("id"),
                        "error": {"code": -32601, "message": str(e)},
                    }
                )
                + "\n"
            )
        sys.stdout.flush()


if __name__ == "__main__":
    main()
