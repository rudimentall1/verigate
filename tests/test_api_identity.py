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
from core.models import AgentIdentity, Capability, PaymentIntent


class ApiIdentityTest(unittest.TestCase):
    def test_identity_bound_authorization_endpoint(self):
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
            agent_key = Ed25519PrivateKey.generate()
            raw = agent_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            identity_id = hashlib.sha256(raw).hexdigest()
            identity = AgentIdentity(
                agent_id="agent-api-identity",
                public_key_b64=base64.b64encode(raw).decode("ascii"),
                key_id=identity_id,
            )

            with TestClient(main.app) as client:
                main._storage.register_identity(identity)
                capability = Capability(
                    capability_id="cap-api-identity",
                    agent_id=identity.agent_id,
                    identity_id=identity_id,
                    allowed_actions=("payment",),
                    allowed_targets=("merchant",),
                    allowed_networks=("base",),
                    allowed_assets=("USDC",),
                )
                main._storage.register_capability(capability)
                intent = PaymentIntent(
                    agent_id=identity.agent_id,
                    payee="merchant",
                    asset="USDC",
                    network="base",
                    amount=1.0,
                    resource="invoice:42",
                    intent_id="intent-api-identity-001",
                    timestamp=1700000000.0,
                )
                signature = sign_action_intent(
                    intent.as_action_intent(), identity_id, agent_key
                )
                payload = {
                    "identity_id": identity_id,
                    "capability_id": capability.capability_id,
                    "agent_id": identity.agent_id,
                    "agent_signature": signature,
                    "intent_id": intent.intent_id,
                    "timestamp": intent.timestamp,
                    "payee": intent.payee,
                    "asset": intent.asset,
                    "network": intent.network,
                    "amount": intent.amount,
                    "resource": intent.resource,
                    "metadata": intent.metadata,
                }
                response = client.post("/v1/authorize/identity", json=payload)
                self.assertEqual(response.status_code, 200)
                execution = response.json()["execution_authorization"]
                self.assertEqual(
                    execution["payload"]["identity_id"], identity_id
                )
                self.assertEqual(
                    execution["payload"]["capability_id"],
                    capability.capability_id,
                )

                tampered = dict(payload)
                tampered["payee"] = "attacker"
                blocked = client.post(
                    "/v1/authorize/identity", json=tampered
                )
                self.assertEqual(blocked.status_code, 403)

                self.assertTrue(
                    main._storage.revoke_identity(identity_id)
                )
                revoked = client.post(
                    "/v1/authorize/identity", json=payload
                )
                self.assertEqual(revoked.status_code, 403)

            main._storage.close()
            main._storage = main._engine = main._policy = None
