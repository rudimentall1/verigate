import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.adversarial import AdversarialVerificationPlane
from core.authorization import AuthorizationService
from core.models import ActionIntent, Capability, Decision, GuardrailDecision
from core.authority_state import DynamicAuthorityService
from core.storage import Storage


class AdversarialVerificationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.tmp.name) / "adversarial.db")
        self.private = Path(self.tmp.name) / "issuer.key"
        self.public = Path(self.tmp.name) / "issuer.pub"
        generate_keypair(self.private, self.public)

        self.capability = Capability(
            capability_id="cap-attack-001",
            agent_id="agent-attack",
            allowed_actions=("payment",),
            allowed_targets=("merchant",),
            allowed_networks=("base",),
            allowed_assets=("USDC",),
            max_per_action={"USDC": 100.0},
        )
        self.action = ActionIntent(
            agent_id="agent-attack",
            action_type="payment",
            target="merchant",
            network="base",
            asset="USDC",
            amount=10.0,
        )

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def authorization(self):
        snapshot = DynamicAuthorityService(self.storage).snapshot(
            self.action.agent_id,
            self.capability.capability_id,
        )
        decision = GuardrailDecision(
            self.action.intent_id,
            self.action.agent_id,
            Decision.ALLOW,
            (),
        )
        return AuthorizationService().issue(
            self.action,
            decision,
            "e" * 64,
            load_private_key(self.private),
            capability=self.capability,
            authority=snapshot,
        )["execution_authorization"]

    def test_all_mutations_are_rejected(self):
        results = AdversarialVerificationPlane.run(
            self.authorization(),
            load_public_key(self.public),
        )
        self.assertEqual(len(results), 10)
        self.assertTrue(all(result.passed for result in results), results)

    def test_assert_all_blocked_is_fail_closed(self):
        results = AdversarialVerificationPlane.assert_all_blocked(
            self.authorization(),
            load_public_key(self.public),
        )
        self.assertEqual(len(results), 10)


    def test_api_exposes_adversarial_verification(self):
        from fastapi.testclient import TestClient
        from api import main

        main.POLICY_PATH = str(Path(self.tmp.name) / "policy.yaml")
        main.DB_PATH = str(Path(self.tmp.name) / "api.db")
        main.PRIVATE_KEY_PATH = str(self.private)
        main.PUBLIC_KEY_PATH = str(self.public)
        Path(main.POLICY_PATH).write_text(
            "allowed_networks: [base]\nallowed_assets: [USDC]\n",
            encoding="utf-8",
        )
        with TestClient(main.app) as client:
            auth = self.authorization()
            response = client.post(
                "/v1/verify/adversarial",
                json={"authorization": auth},
            )
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertTrue(body["baseline_valid"])
            self.assertTrue(body["all_blocked"])
            self.assertEqual(len(body["attacks"]), 10)
        main._storage.close()
        main._storage = main._engine = main._policy = None



if __name__ == "__main__":
    unittest.main()
