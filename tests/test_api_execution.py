import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from api import main
from attest.keys import load_private_key, load_public_key
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter
from core.models import Capability


def test_execution_consume_is_one_time():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        main.POLICY_PATH = str(root / "policy.yaml")
        main.DB_PATH = str(root / "audit.db")
        main.PRIVATE_KEY_PATH = str(root / "issuer.key")
        main.PUBLIC_KEY_PATH = str(root / "issuer.pub")
        Path(main.POLICY_PATH).write_text(
            "allowed_networks: [base]\nallowed_assets: [USDC]\n", encoding="utf-8"
        )
        with TestClient(main.app) as client:
            response = client.post("/v1/authorize", json={
                "agent_id": "agent-exec", "payee": "merchant",
                "asset": "USDC", "network": "base", "amount": 1,
            })
            assert response.status_code == 200
            assert response.json()["execution_authorization"] is None

            auth = response.json()["decision_receipt"]
            assert "signature" in auth
            first = client.post("/v1/execution/consume", json={"authorization": auth})
            assert first.status_code == 200
            assert first.json()["execute"] is False
            assert "payload.action" in first.json()["reason"]
        main._storage.close()
        main._storage = main._engine = main._policy = None


def test_execution_consume_rejects_tampered_authorization():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        main.POLICY_PATH = str(root / "policy.yaml")
        main.DB_PATH = str(root / "audit.db")
        main.PRIVATE_KEY_PATH = str(root / "issuer.key")
        main.PUBLIC_KEY_PATH = str(root / "issuer.pub")
        Path(main.POLICY_PATH).write_text("allowed_networks: [base]\nallowed_assets: [USDC]\n", encoding="utf-8")
        with TestClient(main.app) as client:
            main._storage.register_capability(Capability(
                capability_id="cap-api-exec",
                agent_id="agent-exec",
                allowed_actions=("payment",),
                allowed_targets=("merchant",),
                allowed_networks=("base",),
                allowed_assets=("USDC",),
                max_per_action={"USDC": 10.0},
            ))
            auth = client.post("/v1/authorize/capability", json={
                "agent_id": "agent-exec", "payee": "merchant",
                "asset": "USDC", "network": "base", "amount": 1,
                "capability_id": "cap-api-exec",
            }).json()["execution_authorization"]
            auth["payload"]["agent_id"] = "attacker"
            response = client.post("/v1/execution/consume", json={"authorization": auth})
            assert response.json()["execute"] is False
        main._storage.close()
        main._storage = main._engine = main._policy = None


def test_execution_receipt_can_be_retrieved():
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
            main._storage.register_capability(Capability(
                capability_id="cap-api-receipt",
                agent_id="agent-exec",
                allowed_actions=("payment",),
                allowed_targets=("merchant",),
                allowed_networks=("base",),
                allowed_assets=("USDC",),
                max_per_action={"USDC": 10.0},
            ))
            auth = client.post("/v1/authorize/capability", json={
                "agent_id": "agent-exec", "payee": "merchant",
                "asset": "USDC", "network": "base", "amount": 1,
                "capability_id": "cap-api-receipt",
            }).json()["execution_authorization"]
            router = ExecutionRouter(
                NetworkRegistry(),
                main._storage,
                load_public_key(main.PUBLIC_KEY_PATH),
                load_private_key(main.PRIVATE_KEY_PATH),
            )
            receipt = router.execute_with_receipt(auth, lambda tx: "0xreceipt")
            response = client.get(
                f"/v1/execution/receipts/{auth['payload']['authorization_id']}"
            )
            assert response.status_code == 200
            assert response.json()["payload"]["receipt_id"] == receipt.payload["receipt_id"]
        main._storage.close()
        main._storage = main._engine = main._policy = None
