"""Runnable example of an external agent using the Verigate HTTP client.

The agent identity and capability must already be enrolled by the operator.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

from core.identity import sign_action_intent
from core.models import ActionIntent
from integrations.agent_sdk import load_or_create_agent_key, public_identity
from integrations.http_client import VerigateClient, VerigateError


def main() -> int:
    agent_id = os.environ.get("VERIGATE_AGENT_ID", "external-agent-demo")
    capability_id = os.environ["VERIGATE_CAPABILITY_ID"]
    base_url = os.environ["VERIGATE_BASE_URL"]
    api_key = os.environ.get("VERIGATE_API_KEY")
    tenant_id = os.environ.get("VERIGATE_TENANT_ID")
    key_path = Path(
        os.environ.get("VERIGATE_AGENT_KEY", "~/.config/verigate/agent.key")
    ).expanduser()

    key = load_or_create_agent_key(key_path)
    identity = public_identity(key, agent_id)
    intent = ActionIntent(
        agent_id=agent_id,
        action_type="mcp.tool.call",
        target="demo.create_ticket",
        resource="ticket:demo-001",
        purpose="Create a low-risk demonstration ticket",
        declared_context={"environment": "sandbox"},
        constraints={"max_items": 1},
        intent_id=f"external-agent-{int(time.time())}",
    )
    signed_request = {
        "identity_id": identity["identity_id"],
        "capability_id": capability_id,
        "agent_id": agent_id,
        "agent_signature": sign_action_intent(intent, identity["identity_id"], key),
        **intent.as_dict(),
    }

    client = VerigateClient(
        base_url,
        api_key=api_key,
        tenant_id=tenant_id,
        timeout=float(os.environ.get("VERIGATE_TIMEOUT", "10")),
    )
    try:
        result = client.authorize_and_consume(signed_request)
    except VerigateError as exc:
        print(f"FAIL CLOSED: {exc}")
        return 2

    receipt = result["authorization"].get("decision_receipt", {}).get("payload", {})
    print(f"Decision: {receipt.get('decision', 'UNKNOWN')}")
    if not result["authorized"]:
        print("Protected operation was not executed.")
        return 1

    consumption = result["consumption"]
    if consumption.get("execute") is not True:
        print(f"Execution denied: {consumption.get('reason', 'unknown reason')}")
        print("Protected operation was not executed.")
        return 1

    # Replace this local demonstration with the exact tool call only after
    # successful consumption. No external service is contacted here.
    print("EXECUTION AUTHORIZED. Running the sandbox-only demonstration action.")
    print("DEMO SIDE EFFECT: ticket demo-001 created (local simulation only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
