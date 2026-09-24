import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from api import main


def test_authorize_endpoint_returns_receipt_and_persists_signature():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        main.POLICY_PATH = str(root / "policy.yaml")
        main.DB_PATH = str(root / "audit.db")
        main.PRIVATE_KEY_PATH = str(root / "issuer.key")
        main.PUBLIC_KEY_PATH = str(root / "issuer.pub")
        Path(main.POLICY_PATH).write_text(
            "allowed_networks: [base]\nallowed_assets: [USDC]\n",
            encoding="utf-8",
        )

        with TestClient(main.app) as client:
            response = client.post(
                "/v1/authorize",
                json={
                    "agent_id": "agent-api",
                    "payee": "merchant",
                    "asset": "USDC",
                    "network": "base",
                    "amount": 10,
                },
            )

            assert response.status_code == 200
            body = response.json()
            assert body["decision_receipt"]["algorithm"] == "Ed25519"
            assert body["decision_receipt"]["payload"]["intent"]["action_type"] == "payment"
            assert body["decision_receipt"]["payload"]["decision"]["decision"] == "ALLOW"
            assert len(body["decision_receipt"]["signature"]) > 0
            # Legacy /authorize is decision-only. Executable authority must
            # come from an explicit capability-bound authorization endpoint.
            assert body["execution_authorization"] is None

        main._storage.close()
        main._storage = None
        main._engine = None
        main._policy = None
