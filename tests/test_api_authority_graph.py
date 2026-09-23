import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api import main
from core.models import Capability


class ApiAuthorityGraphTest(unittest.TestCase):
    def test_capability_authority_explanation_endpoint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            main.POLICY_PATH = str(root / "policy.yaml")
            main.DB_PATH = str(root / "authority.db")
            main.PRIVATE_KEY_PATH = str(root / "issuer.key")
            main.PUBLIC_KEY_PATH = str(root / "issuer.pub")
            Path(main.POLICY_PATH).write_text(
                "allowed_networks: [base]\nallowed_assets: [USDC]\n",
                encoding="utf-8",
            )
            with TestClient(main.app) as client:
                capability = Capability(
                    capability_id="cap-graph-api",
                    agent_id="agent-graph",
                    allowed_actions=("payment",),
                    allowed_targets=("merchant",),
                )
                main._storage.register_capability(capability)
                response = client.get(
                    f"/v1/authority/capabilities/{capability.capability_id}"
                )
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["capability"]["capability_id"], capability.capability_id)
                self.assertEqual([item["id"] for item in body["path"]], [capability.capability_id])
            main._storage.close()
            main._storage = main._engine = main._policy = None


if __name__ == "__main__":
    unittest.main()
