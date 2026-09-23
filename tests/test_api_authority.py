import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from api import main
from core.models import Capability


def test_capability_authorization_endpoint_resolves_and_rejects_revoked_capability():
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
            capability = Capability(
                capability_id="cap-api-001",
                agent_id="agent-api",
                allowed_actions=("payment",),
                allowed_targets=("merchant",),
                allowed_networks=("base",),
                allowed_assets=("USDC",),
            )
            main._storage.register_capability(capability)

            response = client.post(
                "/v1/authorize/capability",
                json={
                    "capability_id": capability.capability_id,
                    "agent_id": "agent-api",
                    "payee": "merchant",
                    "asset": "USDC",
                    "network": "base",
                    "amount": 1,
                },
            )
            assert response.status_code == 200
            execution = response.json()["execution_authorization"]
            assert execution["payload"]["capability_id"] == capability.capability_id
            assert execution["payload"]["capability_sha256"] == capability.digest

            assert main._storage.revoke_capability(capability.capability_id) is True
            blocked = client.post(
                "/v1/authorize/capability",
                json={
                    "capability_id": capability.capability_id,
                    "agent_id": "agent-api",
                    "payee": "merchant",
                    "asset": "USDC",
                    "network": "base",
                    "amount": 1,
                },
            )
            assert blocked.status_code == 403

        main._storage.close()
        main._storage = main._engine = main._policy = None
