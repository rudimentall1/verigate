import tempfile
import time
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authority_state import AuthorityState, DynamicAuthorityService
from core.governance import (
    AuthorityGovernanceService,
    GovernanceMember,
    GovernancePolicy,
    MultiPartyAuthorityGovernanceService,
    create_authority_reset,
    create_governance_action,
    sign_governance_approval,
    verify_authority_reset,
    verify_governance_quorum,
)
from core.models import Capability
from core.storage import Storage


class GovernanceResetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.storage = Storage(root / "governance.db")
        self.governance_private = root / "governance.key"
        self.governance_public = root / "governance.pub"
        generate_keypair(self.governance_private, self.governance_public)
        self.capability = Capability(
            capability_id="cap-governance-001",
            agent_id="agent-governance",
            allowed_actions=("payment",),
            allowed_targets=("merchant",),
            allowed_networks=("base",),
            allowed_assets=("USDC",),
            max_per_action={"USDC": 100.0},
        )
        self.storage.register_capability(self.capability)
        self.authority = DynamicAuthorityService(self.storage)
    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def suspend(self):
        self.authority.record_event(
            agent_id=self.capability.agent_id,
            capability_id=self.capability.capability_id,
            event_type="TAMPER_DETECTED",
            evidence_ref="tamper-governance-001",
        )
        return self.authority.snapshot(
            self.capability.agent_id,
            self.capability.capability_id,
        )

    def test_suspension_cannot_self_recover(self):
        snapshot = self.suspend()
        self.assertEqual(snapshot.state, AuthorityState.SUSPENDED)
        for i in range(20):
            self.authority.record_event(
                agent_id=self.capability.agent_id,
                capability_id=self.capability.capability_id,
                event_type="EXECUTION_CONFIRMED",
                evidence_ref=f"success-before-reset-{i}",
            )
        self.assertEqual(
            self.authority.snapshot(
                self.capability.agent_id,
                self.capability.capability_id,
            ).state,
            AuthorityState.SUSPENDED,
        )

    def signed_reset(self, epoch=1, reason="incident reviewed"):
        return create_authority_reset(
            agent_id=self.capability.agent_id,
            capability_id=self.capability.capability_id,
            governor_private_key=load_private_key(self.governance_private),
            epoch=epoch,
            reason=reason,
            issued_at=time.time() + 0.1,
        ).as_dict()

    def test_valid_governance_reset_opens_new_epoch(self):
        self.suspend()
        signed = self.signed_reset()
        result = AuthorityGovernanceService(self.storage).reset(
            signed,
            load_public_key(self.governance_public),
        )
        self.assertEqual(
            result["snapshot"]["state"],
            AuthorityState.PROBATION.value,
        )
        reset = self.storage.latest_authority_reset(
            self.capability.agent_id,
            self.capability.capability_id,
        )
        self.assertEqual(reset["payload"]["epoch"], 1)
        events = self.storage.authority_events(
            agent_id=self.capability.agent_id,
            capability_id=self.capability.capability_id,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "TAMPER_DETECTED")
    def test_old_incident_remains_audit_only_after_reset(self):
        self.suspend()
        signed = self.signed_reset()
        reset_at = signed["payload"]["issued_at"]
        AuthorityGovernanceService(self.storage).reset(
            signed,
            load_public_key(self.governance_public),
        )
        refreshed = self.authority.snapshot(
            self.capability.agent_id,
            self.capability.capability_id,
            now=reset_at + 1,
        )
        self.assertEqual(refreshed.state, AuthorityState.PROBATION)
        self.assertEqual(refreshed.critical_events, 0)

    def test_forged_reset_is_rejected(self):
        self.suspend()
        signed = self.signed_reset()
        signed["payload"]["reason"] = "attacker cleared incident"
        with self.assertRaisesRegex(PermissionError, "invalid or tampered"):
            AuthorityGovernanceService(self.storage).reset(
                signed,
                load_public_key(self.governance_public),
            )

    def test_reset_replay_is_rejected(self):
        self.suspend()
        signed = self.signed_reset()
        service = AuthorityGovernanceService(self.storage)
        service.reset(signed, load_public_key(self.governance_public))
        with self.assertRaisesRegex(PermissionError, "invalid authority reset epoch"):
            service.reset(signed, load_public_key(self.governance_public))

    def test_revoked_capability_cannot_be_resurrected(self):
        self.suspend()
        self.storage.revoke_capability(self.capability.capability_id)
        with self.assertRaisesRegex(
            PermissionError,
            "revoked or expired capability",
        ):
            AuthorityGovernanceService(self.storage).reset(
                self.signed_reset(),
                load_public_key(self.governance_public),
            )

    def test_reset_artifact_verifies_offline(self):
        signed = self.signed_reset()
        ok, reason = verify_authority_reset(
            signed,
            load_public_key(self.governance_public),
        )
        self.assertTrue(ok, reason)


    def test_api_reset_requires_signed_governance_action(self):
        from fastapi.testclient import TestClient
        from api import main

        root = Path(self.tmp.name)
        policy_path = root / "policy.yaml"
        policy_path.write_text(
            "allowed_networks: [base]\nallowed_assets: [USDC]\n",
            encoding="utf-8",
        )
        main.POLICY_PATH = str(policy_path)
        main.DB_PATH = str(root / "api.db")
        main.PRIVATE_KEY_PATH = str(root / "issuer.key")
        main.PUBLIC_KEY_PATH = str(root / "issuer.pub")
        main.GOVERNANCE_PRIVATE_KEY_PATH = str(self.governance_private)
        main.GOVERNANCE_PUBLIC_KEY_PATH = str(self.governance_public)

        with TestClient(main.app) as client:
            public_response = client.get("/v1/governance/public-key")
            self.assertEqual(public_response.status_code, 200)
            self.assertEqual(
                public_response.text.strip(),
                Path(self.governance_public).read_text().strip(),
            )
            main._storage.register_capability(self.capability)
            DynamicAuthorityService(main._storage).record_event(
                agent_id=self.capability.agent_id,
                capability_id=self.capability.capability_id,
                event_type="TAMPER_DETECTED",
                evidence_ref="api-tamper-001",
            )
            DynamicAuthorityService(main._storage).snapshot(
                self.capability.agent_id,
                self.capability.capability_id,
            )
            signed = self.signed_reset()
            response = client.post(
                "/v1/authority/reset",
                json={"reset": signed},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json()["snapshot"]["state"],
                AuthorityState.PROBATION.value,
            )

        main._storage.close()
        main._storage = main._engine = main._policy = None




class MultiPartyGovernanceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.storage = Storage(root / "multiparty.db")
        self.keys = []
        self.members = []
        for i, role in enumerate(("security", "operations", "finance"), start=1):
            private = root / f"gov-{i}.key"
            public = root / f"gov-{i}.pub"
            generate_keypair(private, public)
            self.keys.append(load_private_key(private))
            self.members.append(
                GovernanceMember.from_public_key(
                    load_public_key(public),
                    role,
                )
            )
        self.policy = GovernancePolicy(
            policy_id="prod-authority-governance",
            version=1,
            threshold=2,
            members=tuple(self.members),
            required_roles=(("security", 1), ("operations", 1)),
        )
        self.capability = Capability(
            capability_id="cap-multiparty-001",
            agent_id="agent-multiparty",
            allowed_actions=("payment",),
            allowed_targets=("merchant",),
            allowed_networks=("base",),
            allowed_assets=("USDC",),
            max_per_action={"USDC": 100.0},
        )
        self.storage.register_capability(self.capability)
        self.authority = DynamicAuthorityService(self.storage)

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def suspended_action(self):
        self.authority.record_event(
            agent_id=self.capability.agent_id,
            capability_id=self.capability.capability_id,
            event_type="TAMPER_DETECTED",
            evidence_ref="multiparty-tamper-001",
        )
        issued = time.time() + 0.2
        action = create_governance_action(
            action="AUTHORITY_RESET",
            agent_id=self.capability.agent_id,
            capability_id=self.capability.capability_id,
            epoch=1,
            reason="two-person incident review",
            policy=self.policy,
            issued_at=issued,
            expires_at=issued + 60,
        )
        approvals = [
            sign_governance_approval(
                action,
                role="security",
                private_key=self.keys[0],
                issued_at=issued,
                expires_at=issued + 30,
            ).as_dict(),
            sign_governance_approval(
                action,
                role="operations",
                private_key=self.keys[1],
                issued_at=issued,
                expires_at=issued + 30,
            ).as_dict(),
        ]
        return action, approvals
    def test_two_of_three_quorum_opens_new_epoch(self):
        action, approvals = self.suspended_action()
        result = MultiPartyAuthorityGovernanceService(self.storage).reset(
            action,
            approvals,
            self.policy,
        )
        self.assertEqual(result["snapshot"]["state"], AuthorityState.PROBATION.value)
        self.assertEqual(result["governance_policy_sha256"], self.policy.digest)
        self.assertEqual(
            self.storage.latest_authority_reset(
                self.capability.agent_id,
                self.capability.capability_id,
            )["payload"]["epoch"],
            1,
        )

    def test_one_governor_cannot_reset(self):
        action, approvals = self.suspended_action()
        with self.assertRaisesRegex(PermissionError, "threshold not reached"):
            MultiPartyAuthorityGovernanceService(self.storage).reset(
                action,
                approvals[:1],
                self.policy,
            )

    def test_duplicate_governor_does_not_count_twice(self):
        action, approvals = self.suspended_action()
        with self.assertRaisesRegex(PermissionError, "duplicate governance signer"):
            MultiPartyAuthorityGovernanceService(self.storage).reset(
                action,
                [approvals[0], approvals[0]],
                self.policy,
            )

    def test_required_roles_are_enforced(self):
        action, _ = self.suspended_action()
        approvals = [
            sign_governance_approval(
                action,
                role="finance",
                private_key=self.keys[2],
                issued_at=action.issued_at,
                expires_at=action.issued_at + 30,
            ).as_dict(),
            sign_governance_approval(
                action,
                role="operations",
                private_key=self.keys[1],
                issued_at=action.issued_at,
                expires_at=action.issued_at + 30,
            ).as_dict(),
        ]
        with self.assertRaisesRegex(PermissionError, "required governance role missing"):
            MultiPartyAuthorityGovernanceService(self.storage).reset(
                action,
                approvals,
                self.policy,
            )
    def test_action_tamper_invalidates_all_approvals(self):
        action, approvals = self.suspended_action()
        tampered = action.as_dict()
        tampered["reason"] = "attacker modified governance action"
        ok, reason = verify_governance_quorum(
            tampered,
            approvals,
            self.policy,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "governance approval targets a different action")

    def test_policy_change_invalidates_existing_approvals(self):
        action, approvals = self.suspended_action()
        other_policy = GovernancePolicy(
            policy_id="different-governance-policy",
            version=1,
            threshold=2,
            members=tuple(self.members),
            required_roles=(("security", 1), ("operations", 1)),
        )
        ok, reason = verify_governance_quorum(
            action,
            approvals,
            other_policy,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "governance policy fingerprint mismatch")

    def test_expired_approval_is_rejected(self):
        action, _ = self.suspended_action()
        expired = sign_governance_approval(
            action,
            role="security",
            private_key=self.keys[0],
            issued_at=action.issued_at,
            expires_at=action.issued_at - 1,
        ).as_dict()
        ok, reason = verify_governance_quorum(
            action,
            [expired],
            self.policy,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "governance approval has expired")
    def test_approval_signature_cannot_be_reassigned_to_another_role(self):
        action, approvals = self.suspended_action()
        forged = dict(approvals[0])
        forged["payload"] = dict(forged["payload"])
        forged["payload"]["role"] = "operations"
        ok, reason = verify_governance_quorum(
            action,
            [forged, approvals[1]],
            self.policy,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "governance signer is not authorized for this role")

    def test_quorum_policy_rejects_duplicate_members(self):
        member = self.members[0]
        with self.assertRaisesRegex(ValueError, "duplicate governance member"):
            GovernancePolicy(
                policy_id="invalid",
                version=1,
                threshold=2,
                members=(member, member),
            ).validate()

    def test_governance_approval_replay_is_persistently_blocked(self):
        action, approvals = self.suspended_action()
        service = MultiPartyAuthorityGovernanceService(self.storage)
        service.reset(action, approvals, self.policy)
        with self.assertRaisesRegex(ValueError, "governance approval or authority reset already registered"):
            self.storage.register_authority_reset(
                {
                    "payload": action.as_dict(),
                    "approvals": approvals,
                    "policy": self.policy.as_dict(),
                    "governance_policy_sha256": self.policy.digest,
                    "algorithm": "Ed25519-MULTIPARTY",
                },
                governance_approvals=approvals,
            )

    def test_api_multiparty_reset_endpoint(self):
        from fastapi.testclient import TestClient
        from api import main

        root = Path(self.tmp.name) / "api-multiparty"
        root.mkdir()
        policy_path = root / "policy.yaml"
        policy_path.write_text(
            "allowed_networks: [base]\nallowed_assets: [USDC]\n",
            encoding="utf-8",
        )
        main.POLICY_PATH = str(policy_path)
        main.DB_PATH = str(root / "api.db")
        main.PRIVATE_KEY_PATH = str(root / "issuer.key")
        main.PUBLIC_KEY_PATH = str(root / "issuer.pub")
        main.GOVERNANCE_PRIVATE_KEY_PATH = str(root / "legacy.key")
        main.GOVERNANCE_PUBLIC_KEY_PATH = str(root / "legacy.pub")

        with TestClient(main.app) as client:
            main._governance_policy = self.policy
            main._storage.register_capability(self.capability)
            DynamicAuthorityService(main._storage).record_event(
                agent_id=self.capability.agent_id,
                capability_id=self.capability.capability_id,
                event_type="TAMPER_DETECTED",
                evidence_ref="api-multiparty-tamper-001",
            )
            issued = time.time() + 0.2
            action = create_governance_action(
                action="AUTHORITY_RESET",
                agent_id=self.capability.agent_id,
                capability_id=self.capability.capability_id,
                epoch=1,
                reason="API quorum recovery",
                policy=self.policy,
                issued_at=issued,
                expires_at=issued + 60,
            )
            approvals = [
                sign_governance_approval(
                    action,
                    role="security",
                    private_key=self.keys[0],
                    issued_at=issued,
                    expires_at=issued + 30,
                ).as_dict(),
                sign_governance_approval(
                    action,
                    role="operations",
                    private_key=self.keys[1],
                    issued_at=issued,
                    expires_at=issued + 30,
                ).as_dict(),
            ]
            response = client.post(
                "/v1/authority/reset/multi",
                json={"action": action.as_dict(), "approvals": approvals},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json()["snapshot"]["state"],
                AuthorityState.PROBATION.value,
            )
            policy_response = client.get("/v1/governance/policy")
            self.assertEqual(policy_response.status_code, 200)
            self.assertEqual(
                policy_response.json()["policy_sha256"],
                self.policy.digest,
            )

        main._storage.close()
        main._storage = main._engine = main._policy = None
        main._governance_policy = None

    def test_malformed_governance_action_fails_closed(self):
        action, approvals = self.suspended_action()
        malformed = action.as_dict()
        malformed.pop("expires_at")
        ok, reason = verify_governance_quorum(
            malformed,
            approvals,
            self.policy,
        )
        self.assertFalse(ok)
        self.assertEqual(reason, "invalid governance action expires_at")


if __name__ == "__main__":
    unittest.main()
