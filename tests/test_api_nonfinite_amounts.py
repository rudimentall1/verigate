"""Non-finite JSON numbers must never reach policy evaluation or signed artifacts.

JSON producers in the wild can emit ``Infinity``/``NaN`` (Python's json module
accepts them, and ``1e400`` overflows to ``inf``). Pydantic's ``gt=0`` does not
reject infinity, so before this regression the API happily signed a decision
receipt whose ``amount_exact`` was the string ``"Infinity"`` and could fail
while rendering a response. Input validation must reject these values with a
4xx before any decision, ledger row or signed artifact exists.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api import main


def _setup_paths(root: Path) -> None:
    main.POLICY_PATH = str(root / "policy.yaml")
    main.DB_PATH = str(root / "audit.db")
    main.PRIVATE_KEY_PATH = str(root / "issuer.key")
    main.PUBLIC_KEY_PATH = str(root / "issuer.pub")
    Path(main.POLICY_PATH).write_text(
        "allowed_networks: [base]\n"
        "allowed_assets: [USDC]\n"
        "per_tx_cap:\n"
        "  USDC: 500\n",
        encoding="utf-8",
    )


def _payment_body(amount_literal: str) -> str:
    return (
        '{"agent_id": "nonfinite-agent", '
        '"payee": "0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed", '
        '"asset": "USDC", '
        '"network": "base", '
        f'"amount": {amount_literal}, '
        '"resource": "non-finite probe"}'
    )


def _action_body(timestamp_literal: str) -> str:
    return json.dumps({
        "identity_id": "identity-1",
        "capability_id": "capability-1",
        "agent_id": "nonfinite-agent",
        "agent_signature": "unused-because-validation-fails-first",
        "intent_id": "intent-nonfinite-1",
        "action_type": "mcp.tool.call",
        "target": "example.target",
        "timestamp": 0,
    }).replace('"timestamp": 0', f'"timestamp": {timestamp_literal}')


class NonFiniteRequestFieldTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        _setup_paths(Path(self.tmp.name))

    def tearDown(self):
        if main._storage is not None:
            main._storage.close()
        main._storage = None
        main._engine = None
        main._policy = None
        self.tmp.cleanup()

    def test_non_finite_amounts_are_rejected_before_a_signed_artifact(self):
        with TestClient(main.app, raise_server_exceptions=False) as client:
            for literal in ("Infinity", "-Infinity", "NaN", "1e400"):
                for path in ("/v1/check", "/v1/authorize"):
                    response = client.post(
                        path,
                        content=_payment_body(literal),
                        headers={"content-type": "application/json"},
                    )
                    self.assertEqual(
                        response.status_code,
                        422,
                        f"{path} accepted amount={literal}: {response.text[:200]}",
                    )
                    self.assertNotIn("Infinity", response.text)
            # No decision may be evaluated or persisted for a rejected amount.
            self.assertEqual(main._storage.history("nonfinite-agent", limit=10), [])

    def test_finite_amount_still_returns_a_signed_receipt(self):
        with TestClient(main.app, raise_server_exceptions=False) as client:
            response = client.post(
                "/v1/check",
                content=_payment_body("1.5"),
                headers={"content-type": "application/json"},
            )
            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()["payload"]
            self.assertEqual(payload["decision"], "ALLOW")
            self.assertEqual(response.json()["algorithm"], "Ed25519")

    def test_non_finite_action_timestamp_is_rejected(self):
        with TestClient(main.app, raise_server_exceptions=False) as client:
            for literal in ("Infinity", "-Infinity", "NaN", "1e400"):
                response = client.post(
                    "/v1/actions/authorize",
                    content=_action_body(literal),
                    headers={"content-type": "application/json"},
                )
                self.assertEqual(
                    response.status_code,
                    422,
                    f"action authorize accepted timestamp={literal}: {response.text[:200]}",
                )


if __name__ == "__main__":
    unittest.main()
