#!/usr/bin/env python3
"""Demonstrate the dependency-light EVM execution boundary.

No web3/RPC dependency is required: the adapter verifies the signed action,
consumes the capability once, and hands the exact authorized tx envelope to
a broadcaster callback.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.engine import GuardrailEngine
from core.models import PaymentIntent
from core.policy import Policy
from core.storage import Storage
from enforcement.evm import EVMExecutionAdapter


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="verigate-evm-"))
    private = tmp / "issuer.key"
    public = tmp / "issuer.pub"
    db = tmp / "audit.db"
    generate_keypair(private, public)
    storage = Storage(db)
    engine = GuardrailEngine(Policy.load("policies/default.yaml"), storage)
    tx = {"chain_id": 8453, "to": "0xMerchant", "value_wei": 0, "data": "0xa9059cbb"}
    intent = PaymentIntent(
        agent_id="evm-demo-agent", payee="0xMerchant", asset="USDC",
        network="base", amount=3.0, metadata={"evm_transaction": tx},
    )
    result = engine.authorize(intent, load_private_key(private))
    authorization = result["execution_authorization"]
    adapter = EVMExecutionAdapter(storage, load_public_key(public))
    broadcasted = []

    actual = adapter.execute(
        authorization,
        lambda transaction: broadcasted.append(transaction) or "0xdemo",
    )
    print("Decision:", result["decision_receipt"]["payload"]["decision"]["decision"])
    print("Broadcast:", actual)
    print("Authorized tx:", broadcasted[0])
    try:
        adapter.execute(
            authorization,
            lambda transaction: broadcasted.append(transaction) or "0xreplay",
        )
    except PermissionError as exc:
        print("Replay blocked:", exc)
    print("Broadcast count:", len(broadcasted))
    storage.close()


if __name__ == "__main__":
    main()
