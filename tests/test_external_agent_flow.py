import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from api import main
from core.identity import sign_action_intent
from core.models import ActionIntent
from integrations.agent_sdk import build_agent_enrollment_package, public_identity
from scripts.enroll_agent import enroll


class ExternalAgentFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        main.POLICY_PATH = str(root / "policy.yaml")
        main.DB_PATH = str(root / "audit.db")
        main.PRIVATE_KEY_PATH = str(root / "issuer.key")
        main.PUBLIC_KEY_PATH = str(root / "issuer.pub")
        Path(main.POLICY_PATH).write_text(
            "allowed_networks: [base]\nallowed_assets: [USDC]\n",
            encoding="utf-8",
        )
        self.agent_key = Ed25519PrivateKey.generate()
        self.identity = public_identity(self.agent_key, "external-agent-flow")
        self.capability_id = "external-agent-flow-cap-v1"
        now = time.time()
        self.package = build_agent_enrollment_package(
            self.agent_key,
            agent_id=self.identity["agent_id"],
            capability_id=self.capability_id,
            allowed_actions=["payment"],
            allowed_targets=["merchant-001"],
            allowed_resources=["invoice:flow-test"],
            issued_at=now - 1,
            expires_at=now + 3600,
        )

    def tearDown(self):
        if main._storage is not None:
            main._storage.close()
        main._storage = main._engine = main._policy = None
        self.temp.cleanup()

    def _signed_request(self, *, target="merchant-001", intent_id=None):
        intent = ActionIntent(
            agent_id=self.identity["agent_id"],
            action_type="payment",
            target=target,
            resource="invoice:flow-test",
            amount=Decimal("1.0"),
            amount_exact="1.0",
            asset="USDC",
            network="base",
            intent_id=intent_id or f"external-agent-{time.time_ns()}",
            timestamp=time.time(),
        )
        return {
            "identity_id": self.identity["identity_id"],
            "capability_id": self.capability_id,
            "agent_id": self.identity["agent_id"],
            "agent_signature": sign_action_intent(intent, self.identity["identity_id"], self.agent_key),
            **intent.as_dict(),
        }

    def test_allow_is_consumed_once_and_replay_is_denied(self):
        with TestClient(main.app) as client:
            enroll(main._storage, self.package)
            authorized = client.post("/v1/actions/authorize", json=self._signed_request())
            self.assertEqual(authorized.status_code, 200, authorized.text)
            body = authorized.json()
            self.assertEqual(body["decision_receipt"]["payload"]["decision"], "ALLOW")
            authorization = body["execution_authorization"]
            self.assertIsNotNone(authorization)

            first = client.post("/v1/execution/consume", json={"authorization": authorization})
            self.assertEqual(first.status_code, 200, first.text)
            self.assertTrue(first.json()["execute"], first.json()["reason"])

            replay = client.post("/v1/execution/consume", json={"authorization": authorization})
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertFalse(replay.json()["execute"])

    def test_capability_mismatch_is_blocked_before_execution_authorization(self):
        with TestClient(main.app) as client:
            enroll(main._storage, self.package)
            response = client.post(
                "/v1/actions/authorize",
                json=self._signed_request(target="attacker-controlled-target"),
            )
            self.assertEqual(response.status_code, 403, response.text)

    def test_tampered_authorization_and_expired_authorization_fail_closed(self):
        with TestClient(main.app) as client:
            enroll(main._storage, self.package)
            authorized = client.post("/v1/actions/authorize", json=self._signed_request())
            self.assertEqual(authorized.status_code, 200, authorized.text)
            authorization = authorized.json()["execution_authorization"]

            tampered = {
                **authorization,
                "payload": {**authorization["payload"], "agent_id": "attacker"},
            }
            rejected = client.post("/v1/execution/consume", json={"authorization": tampered})
            self.assertFalse(rejected.json()["execute"])

            with patch(
                "attest.receipt.time.time",
                return_value=authorization["payload"]["expires_at"] + 1,
            ):
                expired = client.post(
                    "/v1/execution/consume",
                    json={"authorization": authorization},
                )
            self.assertFalse(expired.json()["execute"])


if __name__ == "__main__":
    unittest.main()
