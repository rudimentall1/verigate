#!/usr/bin/env python3
"""Demonstrate Verigate enforcing authorization before a real local side effect.

The side effect is intentionally harmless: writing a marker file. The same
ExecutionGate boundary can sit immediately before a real executor call.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.engine import GuardrailEngine
from core.models import PaymentIntent
from core.policy import Policy
from core.storage import Storage
from enforcement.local import ExecutionGate


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="verigate-execution-"))
    private_path = tmp / "issuer.key"
    public_path = tmp / "issuer.pub"
    db_path = tmp / "audit.db"
    marker = tmp / "authorized-side-effect.txt"

    generate_keypair(private_path, public_path)
    storage = Storage(db_path)
    engine = GuardrailEngine(Policy.load("policies/default.yaml"), storage)
    private_key = load_private_key(private_path)
    public_key = load_public_key(public_path)

    intent = PaymentIntent(
        agent_id="execution-demo-agent",
        payee="trusted-data-feed",
        asset="USDC",
        network="base",
        amount=3.0,
    )
    result = engine.authorize(intent, private_key)
    authorization = result["execution_authorization"]

    print("Decision:", result["decision_receipt"]["payload"]["decision"]["decision"])
    print("Authorization issued:", authorization is not None)

    gate = ExecutionGate(storage, public_key)
    gate.execute(
        authorization,
        lambda: marker.write_text("AUTHORIZED\n", encoding="utf-8"),
    )
    print("Side effect:", marker.read_text(encoding="utf-8").strip())

    try:
        gate.execute(
            authorization,
            lambda: marker.write_text("REPLAYED\n", encoding="utf-8"),
        )
    except PermissionError as exc:
        print("Replay blocked:", exc)

    print("Marker remains:", marker.read_text(encoding="utf-8").strip())
    print("Artifacts:", tmp)
    storage.close()


if __name__ == "__main__":
    main()
