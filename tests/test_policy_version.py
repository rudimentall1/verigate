import json
import tempfile
import time
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.receipt import verify_execution_authorization, verify_receipt
from core.engine import GuardrailEngine
from core.policy import Policy
from core.governance import (
    GovernanceMember,
    GovernancePolicy,
    sign_governance_approval,
)
from core.policy_version import (
    GovernedPolicyControlService,
    GovernedPolicyVersionRegistry,
    build_policy_version,
    create_policy_change_action,
    create_policy_control_action,
    sign_policy_version,
    verify_policy_version,
)
from core.models import Capability, PaymentIntent
from core.storage import Storage


class PolicyVersionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.private = root / "issuer.key"
        self.public = root / "issuer.pub"
        generate_keypair(self.private, self.public)
        self.policy_path = root / "policy.yaml"
        self.policy_path.write_text(
            "allowed_networks: [base]\nallowed_assets: [USDC]\n"
            "per_tx_cap:\n  USDC: 100\n",
            encoding="utf-8",
        )
        self.policy = Policy.load(self.policy_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_policy_version_is_signed_and_verifiable(self):
        version = build_policy_version(
            self.policy,
            source_ref=str(self.policy_path),
            version=7,
            parent_sha256="a" * 64,
        )
        signed = sign_policy_version(
            version,
            load_private_key(self.private),
        ).as_dict()
        ok, reason = verify_policy_version(
            signed,
            load_public_key(self.public),
        )
        self.assertTrue(ok, reason)
        self.assertEqual(signed["payload"]["version"], 7)
        self.assertEqual(
            signed["payload"]["policy_sha256"],
            self.policy.digest,
        )

    def test_tampered_policy_version_is_rejected(self):
        version = build_policy_version(
            self.policy,
            source_ref=str(self.policy_path),
        )
        signed = sign_policy_version(
            version,
            load_private_key(self.private),
        ).as_dict()
        signed["payload"]["version"] = 99
        ok, _ = verify_policy_version(
            signed,
            load_public_key(self.public),
        )
        self.assertFalse(ok)

    def test_engine_binds_policy_version_to_receipt_and_authorization(self):
        storage = Storage(Path(self.tmp.name) / "authority.db")
        try:
            engine = GuardrailEngine(
                self.policy,
                storage,
                policy_source_ref=str(self.policy_path),
                policy_version_number=3,
            )
            intent = PaymentIntent(
                agent_id="agent-policy",
                payee="merchant",
                asset="USDC",
                network="base",
                amount=1.0,
            )
            capability = Capability(
                capability_id="cap-policy-version",
                agent_id=intent.agent_id,
                allowed_actions=("payment",),
                allowed_targets=("merchant",),
                allowed_networks=("base",),
                allowed_assets=("USDC",),
                max_per_action={"USDC": 10.0},
            )
            storage.register_capability(capability)
            result = engine.authorize_with_capability(
                intent,
                capability.capability_id,
                load_private_key(self.private),
            )
            receipt = result["decision_receipt"]
            authorization = result["execution_authorization"]
            self.assertIsNotNone(receipt["payload"]["signed_policy_version"])
            self.assertEqual(
                receipt["payload"]["policy_version_sha256"],
                authorization["payload"]["policy_version_sha256"],
            )
            self.assertEqual(
                receipt["payload"]["policy_sha256"],
                receipt["payload"]["signed_policy_version"]["payload"]["policy_sha256"],
            )
            self.assertTrue(
                verify_receipt(
                    receipt,
                    load_public_key(self.public),
                )[0]
            )
            self.assertTrue(
                verify_execution_authorization(
                    authorization,
                    load_public_key(self.public),
                )[0]
            )
            stored = storage.policy_version_by_sha(self.policy.digest)
            self.assertIsNotNone(stored)
            self.assertEqual(stored["payload"]["version"], 3)
        finally:
            storage.close()

    def test_policy_artifact_is_immutable_per_engine(self):
        storage = Storage(Path(self.tmp.name) / "immutable.db")
        try:
            engine = GuardrailEngine(
                self.policy,
                storage,
                policy_source_ref=str(self.policy_path),
                policy_version_number=1,
            )
            first = engine.signed_policy_version(
                load_private_key(self.private)
            )
            second = engine.signed_policy_version(
                load_private_key(self.private)
            )
            self.assertEqual(first, second)
        finally:
            storage.close()


    def test_execution_receipt_preserves_policy_lineage(self):
        from attest.receipt import verify_execution_receipt
        from enforcement.networks import NetworkRegistry
        from enforcement.router import ExecutionRouter

        storage = Storage(Path(self.tmp.name) / "execution-policy.db")
        try:
            engine = GuardrailEngine(
                self.policy,
                storage,
                policy_source_ref=str(self.policy_path),
                policy_version_number=4,
            )
            intent = PaymentIntent(
                agent_id="agent-policy-exec",
                payee="merchant",
                asset="USDC",
                network="base",
                amount=1.0,
            )
            capability = Capability(
                capability_id="cap-policy-lineage",
                agent_id=intent.agent_id,
                allowed_actions=("payment",),
                allowed_targets=("merchant",),
                allowed_networks=("base",),
                allowed_assets=("USDC",),
                max_per_action={"USDC": 10.0},
            )
            storage.register_capability(capability)
            authorization = engine.authorize_with_capability(
                intent,
                capability.capability_id,
                load_private_key(self.private),
            )["execution_authorization"]
            router = ExecutionRouter(
                NetworkRegistry(),
                storage,
                load_public_key(self.public),
                private_key=load_private_key(self.private),
            )
            submitted = router.execute_with_receipt(
                authorization,
                lambda _action: {"tx_hash": "policy-lineage-tx"},
            )
            self.assertEqual(
                submitted.payload["policy_version_sha256"],
                authorization["payload"]["policy_version_sha256"],
            )
            valid, reason = verify_execution_receipt(
                submitted.as_dict(),
                load_public_key(self.public),
                authorization,
            )
            self.assertTrue(valid, reason)
        finally:
            storage.close()



class GovernedPolicyVersionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.issuer_private = root / "issuer.key"
        self.issuer_public = root / "issuer.pub"
        generate_keypair(self.issuer_private, self.issuer_public)
        self.policy_path = root / "governed-policy.yaml"
        self.policy_path.write_text(
            "allowed_networks: [base]\nallowed_assets: [USDC]\n",
            encoding="utf-8",
        )
        self.policy = Policy.load(self.policy_path)
        self.governance_keys = []
        members = []
        for i, role in enumerate(("security", "operations", "finance"), start=1):
            private = root / f"gov-{i}.key"
            public = root / f"gov-{i}.pub"
            generate_keypair(private, public)
            private_key = load_private_key(private)
            self.governance_keys.append(private_key)
            members.append(
                GovernanceMember.from_public_key(
                    load_public_key(public),
                    role,
                )
            )
        self.governance_policy = GovernancePolicy(
            policy_id="policy-governance",
            version=1,
            threshold=2,
            members=tuple(members),
            required_roles=(("security", 1), ("operations", 1)),
            allowed_actions=(
                "AUTHORITY_RESET",
                "POLICY_CHANGE",
                "POLICY_FREEZE",
                "POLICY_ROLLBACK",
            ),
        )
        self.storage = Storage(root / "governed.db")

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def signed_policy(self, version=1, parent_sha256=None):
        return sign_policy_version(
            build_policy_version(
                self.policy,
                source_ref=str(self.policy_path),
                version=version,
                parent_sha256=parent_sha256,
            ),
            load_private_key(self.issuer_private),
        ).as_dict()

    def approvals_for(self, action):
        issued = action.issued_at
        return [
            sign_governance_approval(
                action,
                role="security",
                private_key=self.governance_keys[0],
                issued_at=issued,
                expires_at=issued + 30,
            ).as_dict(),
            sign_governance_approval(
                action,
                role="operations",
                private_key=self.governance_keys[1],
                issued_at=issued,
                expires_at=issued + 30,
            ).as_dict(),
        ]
    def publish(self, signed):
        action = create_policy_change_action(
            signed,
            governance_policy=self.governance_policy,
            reason="approve exact policy change",
            issued_at=time.time() + 0.2,
            expires_at=time.time() + 60,
        )
        return action, GovernedPolicyVersionRegistry(self.storage).publish(
            signed,
            action,
            self.approvals_for(action),
            self.governance_policy,
            load_public_key(self.issuer_public),
        )

    def test_governed_policy_publish_requires_quorum(self):
        signed = self.signed_policy()
        action = create_policy_change_action(
            signed,
            governance_policy=self.governance_policy,
            reason="two-person policy approval",
            issued_at=time.time() + 0.2,
            expires_at=time.time() + 60,
        )
        registry = GovernedPolicyVersionRegistry(self.storage)
        with self.assertRaisesRegex(PermissionError, "threshold not reached"):
            registry.publish(
                signed,
                action,
                [self.approvals_for(action)[0]],
                self.governance_policy,
                load_public_key(self.issuer_public),
            )

    def test_governed_policy_publish_succeeds_with_exact_quorum(self):
        signed = self.signed_policy()
        action, result = self.publish(signed)
        self.assertEqual(result["policy"]["payload"]["version"], 1)
        self.assertEqual(result["governance_action"]["action"], "POLICY_CHANGE")
        self.assertEqual(
            result["governance_policy_sha256"],
            self.governance_policy.digest,
        )
        governed = self.storage.governed_policy_change_by_sha(
            signed["payload"]["policy_sha256"]
        )
        self.assertIsNotNone(governed)
        self.assertEqual(
            governed["governance_action"]["action_id"],
            action.action_id,
        )
    def test_policy_action_tamper_is_rejected(self):
        signed = self.signed_policy()
        action = create_policy_change_action(
            signed,
            governance_policy=self.governance_policy,
            reason="policy review",
            issued_at=time.time() + 0.2,
            expires_at=time.time() + 60,
        )
        approvals = self.approvals_for(action)
        tampered = dict(action.as_dict())
        tampered["policy_sha256"] = "f" * 64
        with self.assertRaisesRegex(
            PermissionError,
            "different action|policy governance action does not match",
        ):
            GovernedPolicyVersionRegistry(self.storage).publish(
                signed,
                tampered,
                approvals,
                self.governance_policy,
                load_public_key(self.issuer_public),
            )

    def test_signed_policy_tamper_is_rejected(self):
        signed = self.signed_policy()
        action = create_policy_change_action(
            signed,
            governance_policy=self.governance_policy,
            reason="policy review",
            issued_at=time.time() + 0.2,
            expires_at=time.time() + 60,
        )
        signed["payload"]["version"] = 2
        with self.assertRaisesRegex(PermissionError, "invalid or tampered"):
            GovernedPolicyVersionRegistry(self.storage).publish(
                signed,
                action,
                self.approvals_for(action),
                self.governance_policy,
                load_public_key(self.issuer_public),
            )

    def test_policy_lineage_is_monotonic_and_parent_bound(self):
        first = self.signed_policy()
        _, _ = self.publish(first)
        self.policy_path.write_text(
            "allowed_networks: [base, arbitrum]\nallowed_assets: [USDC]\n",
            encoding="utf-8",
        )
        self.policy = Policy.load(self.policy_path)
        second = self.signed_policy(
            version=2,
            parent_sha256=first["payload"]["policy_sha256"],
        )
        _, result = self.publish(second)
        self.assertEqual(result["policy"]["payload"]["version"], 2)

        self.policy_path.write_text(
            "allowed_networks: [base, arbitrum, ethereum]\nallowed_assets: [USDC]\n",
            encoding="utf-8",
        )
        self.policy = Policy.load(self.policy_path)
        bad = self.signed_policy(
            version=4,
            parent_sha256=second["payload"]["policy_sha256"],
        )
        action = create_policy_change_action(
            bad,
            governance_policy=self.governance_policy,
            reason="invalid lineage",
            issued_at=time.time() + 0.2,
            expires_at=time.time() + 60,
        )
        with self.assertRaisesRegex(PermissionError, "increment monotonically"):
            GovernedPolicyVersionRegistry(self.storage).publish(
                bad,
                action,
                self.approvals_for(action),
                self.governance_policy,
                load_public_key(self.issuer_public),
            )
    def test_policy_publish_replay_is_persistently_blocked(self):
        signed = self.signed_policy()
        action, _ = self.publish(signed)
        with self.assertRaisesRegex(
            PermissionError,
            "already published",
        ):
            GovernedPolicyVersionRegistry(self.storage).publish(
                signed,
                action,
                self.approvals_for(action),
                self.governance_policy,
                load_public_key(self.issuer_public),
            )

    def test_strict_engine_rejects_ungoverned_policy(self):
        engine = GuardrailEngine(
            self.policy,
            self.storage,
            policy_source_ref=str(self.policy_path),
            policy_version_number=1,
            require_governed_policy=True,
        )
        with self.assertRaisesRegex(PermissionError, "not governance-approved"):
            engine.signed_policy_version(
                load_private_key(self.issuer_private)
            )

    def test_strict_engine_accepts_governed_policy(self):
        signed = self.signed_policy()
        self.publish(signed)
        engine = GuardrailEngine(
            self.policy,
            self.storage,
            policy_source_ref=str(self.policy_path),
            policy_version_number=1,
            require_governed_policy=True,
        )
        artifact = engine.signed_policy_version(
            load_private_key(self.issuer_private)
        )
        self.assertEqual(
            artifact["payload"]["policy_sha256"],
            self.policy.digest,
        )

    def test_governance_policy_digest_is_part_of_action(self):
        signed = self.signed_policy()
        action = create_policy_change_action(
            signed,
            governance_policy=self.governance_policy,
            reason="digest binding",
        )
        self.assertEqual(
            action.as_dict()["governance_policy_sha256"],
            self.governance_policy.digest,
        )


    def test_api_governed_policy_publication(self):
        from fastapi.testclient import TestClient
        from api import main

        root = Path(self.tmp.name) / "api"
        root.mkdir()
        governance_path = root / "governance-policy.json"
        governance_path.write_text(
            json.dumps(self.governance_policy.as_dict()),
            encoding="utf-8",
        )
        main.POLICY_PATH = str(self.policy_path)
        main.DB_PATH = str(root / "api.db")
        main.PRIVATE_KEY_PATH = str(self.issuer_private)
        main.PUBLIC_KEY_PATH = str(self.issuer_public)
        main.GOVERNANCE_POLICY_PATH = str(governance_path)
        main.REQUIRE_GOVERNED_POLICY = False

        signed = self.signed_policy()
        action = create_policy_change_action(
            signed,
            governance_policy=self.governance_policy,
            reason="API policy publication",
            issued_at=time.time() + 0.2,
            expires_at=time.time() + 60,
        )
        with TestClient(main.app) as client:
            response = client.post(
                "/v1/policies/governed/publish",
                json={
                    "policy": signed,
                    "governance_action": action.as_dict(),
                    "approvals": self.approvals_for(action),
                },
            )
            self.assertEqual(response.status_code, 200)
            governed = client.get(
                f"/v1/policies/governed/{signed['payload']['policy_sha256']}"
            )
            self.assertEqual(governed.status_code, 200)
            self.assertEqual(
                governed.json()["governance_policy_sha256"],
                self.governance_policy.digest,
            )

        main._storage = main._engine = main._policy = None
        main._governance_policy = None

    def control_approvals(self, action):
        return self.approvals_for(action)

    def test_policy_freeze_blocks_cached_engine_authority(self):
        signed = self.signed_policy()
        self.publish(signed)
        engine = GuardrailEngine(
            self.policy,
            self.storage,
            policy_source_ref=str(self.policy_path),
            policy_version_number=1,
            require_governed_policy=True,
        )
        engine.signed_policy_version(load_private_key(self.issuer_private))
        action = create_policy_control_action(
            action="POLICY_FREEZE",
            policy_id=signed["payload"]["policy_id"],
            current_policy_sha256=signed["payload"]["policy_sha256"],
            governance_policy=self.governance_policy,
            reason="emergency freeze",
            issued_at=time.time() + 0.2,
            expires_at=time.time() + 60,
        )
        result = GovernedPolicyControlService(self.storage).apply(
            action,
            self.control_approvals(action),
            self.governance_policy,
        )
        self.assertTrue(result["frozen"])
        with self.assertRaisesRegex(PermissionError, "frozen"):
            engine.signed_policy_version(load_private_key(self.issuer_private))

    def test_policy_freeze_replay_is_persistently_blocked(self):
        signed = self.signed_policy()
        self.publish(signed)
        action = create_policy_control_action(
            action="POLICY_FREEZE",
            policy_id=signed["payload"]["policy_id"],
            current_policy_sha256=signed["payload"]["policy_sha256"],
            governance_policy=self.governance_policy,
            reason="freeze replay test",
            issued_at=time.time() + 0.2,
            expires_at=time.time() + 60,
        )
        approvals = self.control_approvals(action)
        service = GovernedPolicyControlService(self.storage)
        service.apply(action, approvals, self.governance_policy)
        with self.assertRaisesRegex(PermissionError, "already registered"):
            service.apply(action, approvals, self.governance_policy)

    def test_policy_rollback_reactivates_previous_governed_version(self):
        first = self.signed_policy()
        self.publish(first)
        self.policy_path.write_text(
            "allowed_networks: [base, arbitrum]\nallowed_assets: [USDC]\n",
            encoding="utf-8",
        )
        self.policy = Policy.load(self.policy_path)
        second = self.signed_policy(
            version=2,
            parent_sha256=first["payload"]["policy_sha256"],
        )
        self.publish(second)

        rollback = create_policy_control_action(
            action="POLICY_ROLLBACK",
            policy_id=second["payload"]["policy_id"],
            current_policy_sha256=second["payload"]["policy_sha256"],
            target_policy_sha256=first["payload"]["policy_sha256"],
            target_version=1,
            governance_policy=self.governance_policy,
            reason="rollback compromised policy",
            issued_at=time.time() + 0.2,
            expires_at=time.time() + 60,
        )
        result = GovernedPolicyControlService(self.storage).apply(
            rollback,
            self.control_approvals(rollback),
            self.governance_policy,
        )
        self.assertFalse(result["frozen"])
        self.assertEqual(
            result["active_policy_sha256"],
            first["payload"]["policy_sha256"],
        )

        strict_v2 = GuardrailEngine(
            self.policy,
            self.storage,
            policy_source_ref=str(self.policy_path),
            policy_version_number=2,
            policy_parent_sha256=first["payload"]["policy_sha256"],
            require_governed_policy=True,
        )
        with self.assertRaisesRegex(PermissionError, "not the active governed policy"):
            strict_v2.signed_policy_version(load_private_key(self.issuer_private))

        self.policy_path.write_text(
            "allowed_networks: [base]\nallowed_assets: [USDC]\n",
            encoding="utf-8",
        )
        self.policy = Policy.load(self.policy_path)
        strict_v1 = GuardrailEngine(
            self.policy,
            self.storage,
            policy_source_ref=str(self.policy_path),
            policy_version_number=1,
            require_governed_policy=True,
        )
        artifact = strict_v1.signed_policy_version(load_private_key(self.issuer_private))
        self.assertEqual(
            artifact["payload"]["policy_sha256"],
            first["payload"]["policy_sha256"],
        )

    def test_rollback_requires_real_governed_target(self):
        signed = self.signed_policy()
        self.publish(signed)
        fake = "f" * 64
        with self.assertRaisesRegex(PermissionError, "rollback target is not governed"):
            action = create_policy_control_action(
                action="POLICY_ROLLBACK",
                policy_id=signed["payload"]["policy_id"],
                current_policy_sha256=signed["payload"]["policy_sha256"],
                target_policy_sha256=fake,
                target_version=1,
                governance_policy=self.governance_policy,
                reason="invalid rollback target",
            )
            GovernedPolicyControlService(self.storage).apply(
                action,
                self.control_approvals(action),
                self.governance_policy,
            )

    def test_control_action_policy_digest_is_bound(self):
        signed = self.signed_policy()
        self.publish(signed)
        action = create_policy_control_action(
            action="POLICY_FREEZE",
            policy_id=signed["payload"]["policy_id"],
            current_policy_sha256=signed["payload"]["policy_sha256"],
            governance_policy=self.governance_policy,
            reason="digest binding",
        )
        tampered = dict(action.as_dict())
        tampered["current_policy_sha256"] = "0" * 64
        with self.assertRaisesRegex(PermissionError, "different action"):
            GovernedPolicyControlService(self.storage).apply(
                tampered,
                self.control_approvals(action),
                self.governance_policy,
            )


    def test_api_policy_freeze_control(self):
        from fastapi.testclient import TestClient
        from api import main

        root = Path(self.tmp.name) / "freeze-api"
        root.mkdir()
        governance_path = root / "governance-policy.json"
        governance_path.write_text(
            json.dumps(self.governance_policy.as_dict()),
            encoding="utf-8",
        )
        main.POLICY_PATH = str(self.policy_path)
        main.DB_PATH = str(root / "api.db")
        main.PRIVATE_KEY_PATH = str(self.issuer_private)
        main.PUBLIC_KEY_PATH = str(self.issuer_public)
        main.GOVERNANCE_POLICY_PATH = str(governance_path)
        main.REQUIRE_GOVERNED_POLICY = False

        signed = self.signed_policy()
        publish_action = create_policy_change_action(
            signed,
            governance_policy=self.governance_policy,
            reason="API freeze setup",
            issued_at=time.time() + 0.2,
            expires_at=time.time() + 60,
        )
        freeze_action = create_policy_control_action(
            action="POLICY_FREEZE",
            policy_id=signed["payload"]["policy_id"],
            current_policy_sha256=signed["payload"]["policy_sha256"],
            governance_policy=self.governance_policy,
            reason="API emergency freeze",
            issued_at=time.time() + 0.2,
            expires_at=time.time() + 60,
        )
        with TestClient(main.app) as client:
            published = client.post(
                "/v1/policies/governed/publish",
                json={
                    "policy": signed,
                    "governance_action": publish_action.as_dict(),
                    "approvals": self.approvals_for(publish_action),
                },
            )
            self.assertEqual(published.status_code, 200)
            frozen = client.post(
                "/v1/policies/governed/freeze",
                json={
                    "governance_action": freeze_action.as_dict(),
                    "approvals": self.control_approvals(freeze_action),
                },
            )
            self.assertEqual(frozen.status_code, 200)
            self.assertTrue(frozen.json()["frozen"])
            control = client.get(
                f"/v1/policies/governed/control/{signed['payload']['policy_id']}"
            )
            self.assertEqual(control.status_code, 200)
            self.assertTrue(control.json()["frozen"])

        main._storage = main._engine = main._policy = None
        main._governance_policy = None

if __name__ == "__main__":
    unittest.main()
