import tempfile
import time
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authority_state import AuthorityState, DynamicAuthorityService
from core.governance import (
    AuthorityGovernanceService,
    create_authority_reset,
    verify_authority_reset,
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




if __name__ == "__main__":
    unittest.main()
