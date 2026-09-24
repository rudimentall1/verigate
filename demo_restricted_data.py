#!/usr/bin/env python3
"""Restricted-data authority demo: scope mismatch blocks the side effect."""
from __future__ import annotations

import tempfile
from pathlib import Path

from attest.keys import generate_keypair, load_private_key
from core.engine import GuardrailEngine
from core.models import ActionIntent, Capability, AgentIdentity
from core.policy import Policy
from core.storage import Storage


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="verigate-restricted-") as td:
        root = Path(td)
        policy_path = root / "policy.yaml"
        policy_path.write_text(
            "allowed_action_types: [data.read]\n"
            "allowed_targets: [medicare.public-records]\n",
            encoding="utf-8",
        )
        issuer = root / "issuer.key"
        issuer_pub = root / "issuer.pub"
        generate_keypair(issuer, issuer_pub)
        storage = Storage(root / "audit.db")
        try:
            engine = GuardrailEngine(Policy.load(policy_path), storage)
            action = ActionIntent(
                agent_id="research-agent",
                action_type="data.read",
                target="medicare.restricted-records",
                resource="patient-files",
                purpose="research",
                declared_context={"classification": "restricted"},
                intent_id="restricted-data-demo",
            )
            capability = Capability(
                capability_id="cap-public-data",
                agent_id=action.agent_id,
                allowed_actions=("data.read",),
                allowed_targets=("medicare.restricted-records",),
            )
            storage.register_capability(capability)
            decision = engine.evaluate_action(action)
            result = engine._authorize_control_plane(
                action,
                load_private_key(issuer),
                capability_id=capability.capability_id,
                decision=decision,
            )
            decision = result["decision_receipt"]["payload"]["decision"]
            print("VERIGATE | RESTRICTED-DATA AUTHORITY DEMO")
            print("Agent: research-agent")
            print("Requested: medicare.restricted-records")
            print("Granted scope: medicare.public-records")
            print(f"Decision: {decision['decision']}")
            print("Rule evidence:", decision["matched_rules"])
            print("Execution authorization issued:", result["execution_authorization"] is not None)
            side_effects = []
            authorization = result["execution_authorization"]
            if authorization is not None:
                side_effects.append("UNEXPECTED EXECUTION")
            print("Side effects:", side_effects or "NONE")
            print("Result: restricted data was never exposed.")
        finally:
            storage.close()


if __name__ == "__main__":
    main()
