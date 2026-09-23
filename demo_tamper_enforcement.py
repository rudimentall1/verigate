#!/usr/bin/env python3
"""Visible proof that authorized actions stop executing after tampering."""
from __future__ import annotations

import tempfile
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authorization import AuthorizationService
from core.models import ActionIntent, Decision, GuardrailDecision
from core.storage import Storage
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter


def make_authorization(private_key):
    intent = ActionIntent(
        agent_id="demo-agent",
        action_type="tool.execute",
        target="approved-merchant",
        resource="https://api.approved.example/pay",
        amount=500.0,
        asset="USDC",
        network="base",
        metadata={
            "tool_endpoint": "https://api.approved.example/pay",
            "evm_transaction": {
                "chain_id": 8453,
                "to": "0xApproved",
                "value_wei": 500_000_000,
                "data": "0x1234",
            },
        },
    )
    decision = GuardrailDecision(
        intent_id=intent.intent_id,
        agent_id=intent.agent_id,
        decision=Decision.ALLOW,
        matched_rules=(),
    )
    return AuthorizationService().issue(
        intent,
        decision,
        "tamper-demo-policy",
        private_key,
        nonce=intent.intent_id,
    )["execution_authorization"]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="verigate-tamper-") as td:
        root = Path(td)
        private = root / "issuer.key"
        public = root / "issuer.pub"
        database = root / "audit.db"
        generate_keypair(private, public)

        storage = Storage(database)
        router = ExecutionRouter(
            NetworkRegistry(),
            storage,
            load_public_key(public),
        )
        signing_key = load_private_key(private)

        try:
            print("==============================================================")
            print("VERIGATE | TAMPERED ACTION ENFORCEMENT")
            print("==============================================================")
            print("Authorized action: Buy Gold for $500")
            print("Destination: 0xApproved")
            print("")
            print("1) Tool endpoint is changed after ALLOW")
            authorization = make_authorization(signing_key)
            authorization["payload"]["action"]["metadata"]["tool_endpoint"] = (
                "https://attacker.example/collect"
            )
            calls = []
            try:
                router.execute(
                    authorization,
                    lambda tx: calls.append(tx) or "tx-hash",
                )
            except (PermissionError, ValueError) as exc:
                print("VERIGATE: BLOCK")
                print(f"Reason: {exc}")
            print("Broadcasts:", len(calls))
            print("")
            print("2) Transaction destination is changed after ALLOW")
            authorization = make_authorization(signing_key)
            authorization["payload"]["action"]["metadata"]["evm_transaction"]["to"] = (
                "0xAttacker"
            )
            calls = []
            try:
                router.execute(
                    authorization,
                    lambda tx: calls.append(tx) or "tx-hash",
                )
            except (PermissionError, ValueError) as exc:
                print("VERIGATE: BLOCK")
                print(f"Reason: {exc}")
            print("Broadcasts:", len(calls))
            print("")
            print("3) Untampered authorization")
            authorization = make_authorization(signing_key)
            calls = []
            result = router.execute(
                authorization,
                lambda tx: calls.append(tx) or "demo-tx-hash",
            )
            print("VERIGATE: ALLOW")
            print("Broadcast result:", result)
            print("Broadcasts:", len(calls))
            print("")
            print("CORE RULE: the execution boundary consumes the signed")
            print("authorization for the exact action that was approved.")
            print("Any mutation changes the action fingerprint and cannot execute.")
            print("==============================================================")
        finally:
            storage.close()


if __name__ == "__main__":
    main()
