import base64
import hashlib
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from api import main
from core.identity import sign_action_intent
from core.models import ActionIntent, AgentIdentity, Capability


class UniversalActionApiTest(unittest.TestCase):
    def test_generic_action_is_authorized_without_payment_model(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            main.POLICY_PATH = str(root / "policy.yaml")
            main.DB_PATH = str(root / "audit.db")
            main.PRIVATE_KEY_PATH = str(root / "issuer.key")
            main.PUBLIC_KEY_PATH = str(root / "issuer.pub")
            Path(main.POLICY_PATH).write_text(
                "allowed_action_types: [mcp.tool.call]\n"
                "allowed_targets: [github.create_issue]\n",
                encoding="utf-8",
            )

            agent_key = Ed25519PrivateKey.generate()
            raw = agent_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            identity_id = hashlib.sha256(raw).hexdigest()
            identity = AgentIdentity(
                agent_id="agent-mcp",
                public_key_b64=base64.b64encode(raw).decode("ascii"),
                key_id=identity_id,
            )

            with TestClient(main.app) as client:
                main._storage.register_identity(identity)
                capability = Capability(
                    capability_id="cap-mcp-001",
                    agent_id=identity.agent_id,
                    identity_id=identity_id,
                    allowed_actions=("mcp.tool.call",),
                    allowed_targets=("github.create_issue",),
                )
                main._storage.register_capability(capability)

                action = ActionIntent(
                    agent_id=identity.agent_id,
                    action_type="mcp.tool.call",
                    target="github.create_issue",
                    resource="repo:rudimentall1/verigate",
                    metadata={"tool": "github.create_issue", "arguments": {"title": "hello"}},
                    intent_id="action-mcp-001",
                    timestamp=1700000000.0,
                )
                signature = sign_action_intent(action, identity_id, agent_key)
                response = client.post("/v1/actions/authorize", json={
                    "identity_id": identity_id,
                    "capability_id": capability.capability_id,
                    "agent_id": action.agent_id,
                    "agent_signature": signature,
                    "intent_id": action.intent_id,
                    "timestamp": action.timestamp,
                    "action_type": action.action_type,
                    "target": action.target,
                    "resource": action.resource,
                    "metadata": action.metadata,
                })

                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(
                    body["decision_receipt"]["payload"]["intent"]["action_type"],
                    "mcp.tool.call",
                )
                self.assertEqual(
                    body["execution_authorization"]["payload"]["action"]["target"],
                    "github.create_issue",
                )

            main._storage.close()
            main._storage = main._engine = main._policy = None

    def test_generic_target_outside_policy_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            main.POLICY_PATH = str(root / "policy.yaml")
            main.DB_PATH = str(root / "audit.db")
            main.PRIVATE_KEY_PATH = str(root / "issuer.key")
            main.PUBLIC_KEY_PATH = str(root / "issuer.pub")
            Path(main.POLICY_PATH).write_text(
                "allowed_action_types: [mcp.tool.call]\n"
                "allowed_targets: [github.create_issue]\n",
                encoding="utf-8",
            )
            agent_key = Ed25519PrivateKey.generate()
            raw = agent_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            identity_id = hashlib.sha256(raw).hexdigest()
            identity = AgentIdentity(
                agent_id="agent-mcp-block",
                public_key_b64=base64.b64encode(raw).decode("ascii"),
                key_id=identity_id,
            )
            with TestClient(main.app) as client:
                main._storage.register_identity(identity)
                capability = Capability(
                    capability_id="cap-mcp-block",
                    agent_id=identity.agent_id,
                    identity_id=identity_id,
                    allowed_actions=("mcp.tool.call",),
                    allowed_targets=("github.delete_repository",),
                )
                main._storage.register_capability(capability)
                action = ActionIntent(
                    agent_id=identity.agent_id,
                    action_type="mcp.tool.call",
                    target="github.delete_repository",
                    intent_id="action-mcp-block",
                    timestamp=1700000000.0,
                )
                signature = sign_action_intent(action, identity_id, agent_key)
                response = client.post("/v1/actions/authorize", json={
                    "identity_id": identity_id,
                    "capability_id": capability.capability_id,
                    "agent_id": action.agent_id,
                    "agent_signature": signature,
                    "intent_id": action.intent_id,
                    "timestamp": action.timestamp,
                    "action_type": action.action_type,
                    "target": action.target,
                })
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["decision_receipt"]["payload"]["decision"]["decision"], "BLOCK")
                self.assertIsNone(body["execution_authorization"])
            main._storage.close()
            main._storage = main._engine = main._policy = None


if __name__ == "__main__":
    unittest.main()
