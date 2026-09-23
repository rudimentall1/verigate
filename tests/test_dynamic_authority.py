import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.receipt import (
    verify_execution_authorization,
)
from core.authority_state import (
    AuthorityPolicy,
    AuthorityState,
    DynamicAuthorityService,
)
from core.models import ActionIntent, Capability
from core.storage import Storage


class DynamicAuthorityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.tmp.name) / "authority.db")
        self.service = DynamicAuthorityService(
            self.storage,
            AuthorityPolicy(),
        )
        self.capability = Capability(
            capability_id="cap-dynamic-001",
            agent_id="agent-dynamic",
            allowed_actions=("payment", "irreversible_operation"),
            allowed_targets=("merchant",),
            allowed_networks=("base",),
            allowed_assets=("USDC",),
            max_per_action={"USDC": 500.0},
        )
        self.action = ActionIntent(
            agent_id="agent-dynamic",
            action_type="payment",
            target="merchant",
            network="base",
            asset="USDC",
            amount=25.0,
        )

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def success(self, ref: str):
        return self.service.record_event(
            agent_id=self.capability.agent_id,
            capability_id=self.capability.capability_id,
            event_type="EXECUTION_CONFIRMED",
            evidence_ref=ref,
        )

    def test_starts_in_probation_and_caps_amount(self):
        snapshot = self.service.snapshot(
            self.capability.agent_id,
            self.capability.capability_id,
        )
        self.assertEqual(snapshot.state, AuthorityState.PROBATION)
        self.assertAlmostEqual(snapshot.multiplier, 0.10)
        allowed = ActionIntent(**{**self.action.__dict__, "amount": 50.0})
        self.service.assert_action(self.capability, allowed)
        blocked = ActionIntent(**{**self.action.__dict__, "amount": 50.01})
        with self.assertRaisesRegex(PermissionError, "dynamic authority limit"):
            self.service.assert_action(self.capability, blocked)

    def test_success_history_promotes_to_standard_then_elevated(self):
        for i in range(5):
            self.success(f"ok-{i}")
        standard = self.service.snapshot(
            self.capability.agent_id,
            self.capability.capability_id,
        )
        self.assertEqual(standard.state, AuthorityState.STANDARD)
        self.assertAlmostEqual(standard.multiplier, 0.50)

        for i in range(5, 20):
            self.success(f"ok-{i}")
        elevated = self.service.snapshot(
            self.capability.agent_id,
            self.capability.capability_id,
        )
        self.assertEqual(elevated.state, AuthorityState.ELEVATED)
        self.assertAlmostEqual(elevated.multiplier, 1.00)
    def test_adverse_history_reduces_authority(self):
        for i in range(2):
            self.service.record_event(
                agent_id=self.capability.agent_id,
                capability_id=self.capability.capability_id,
                event_type="EXECUTION_FAILED",
                evidence_ref=f"fail-{i}",
            )
        snapshot = self.service.snapshot(
            self.capability.agent_id,
            self.capability.capability_id,
        )
        self.assertEqual(snapshot.state, AuthorityState.LIMITED)
        self.assertAlmostEqual(snapshot.multiplier, 0.25)

    def test_critical_event_latches_suspension(self):
        self.service.record_event(
            agent_id=self.capability.agent_id,
            capability_id=self.capability.capability_id,
            event_type="TAMPER_DETECTED",
            evidence_ref="tamper-1",
        )
        first = self.service.snapshot(
            self.capability.agent_id,
            self.capability.capability_id,
        )
        self.assertEqual(first.state, AuthorityState.SUSPENDED)
        with self.assertRaisesRegex(PermissionError, "suspended"):
            self.service.assert_action(self.capability, self.action)

        later = self.service.snapshot(
            self.capability.agent_id,
            self.capability.capability_id,
            now=first.evaluated_at + 365 * 24 * 3600,
        )
        self.assertEqual(later.state, AuthorityState.SUSPENDED)

    def test_elevated_only_action_requires_real_history(self):
        irreversible = ActionIntent(
            **{**self.action.__dict__, "action_type": "irreversible_operation"}
        )
        with self.assertRaisesRegex(PermissionError, "requires elevated"):
            self.service.assert_action(self.capability, irreversible)
        for i in range(20):
            self.success(f"irreversible-ready-{i}")
        self.service.assert_action(self.capability, irreversible)

    def test_duplicate_evidence_is_idempotent(self):
        first = self.success("same-receipt")
        second = self.success("same-receipt")
        self.assertEqual(first["event_id"], second["event_id"])
        events = self.storage.authority_events(
            agent_id=self.capability.agent_id,
            capability_id=self.capability.capability_id,
        )
        self.assertEqual(len(events), 1)

    def test_snapshot_digest_can_be_bound_to_signed_authorization(self):
        for i in range(5):
            self.success(f"auth-ok-{i}")
        snapshot = self.service.snapshot(
            self.capability.agent_id,
            self.capability.capability_id,
        )

        private_path = Path(self.tmp.name) / "issuer.key"
        public_path = Path(self.tmp.name) / "issuer.pub"
        generate_keypair(private_path, public_path)
        from core.authorization import AuthorizationService
        from core.models import Decision, GuardrailDecision

        decision = GuardrailDecision(
            self.action.intent_id,
            self.action.agent_id,
            Decision.ALLOW,
            (),
        )
        auth = AuthorizationService().issue(
            self.action,
            decision,
            "e" * 64,
            load_private_key(private_path),
            capability=self.capability,
            authority=snapshot,
        )["execution_authorization"]

        self.assertEqual(
            auth["payload"]["authority_state_sha256"],
            snapshot.digest,
        )
        self.assertTrue(
            verify_execution_authorization(
                auth,
                load_public_key(public_path),
            )[0]
        )

        tampered = {
            **auth,
            "payload": {
                **auth["payload"],
                "authority_multiplier": 1.0,
            },
        }
        self.assertFalse(
            verify_execution_authorization(
                tampered,
                load_public_key(public_path),
            )[0]
        )

    def test_confirmed_execution_feeds_back_into_authority_history(self):
        from core.authorization import AuthorizationService
        from core.models import Decision, GuardrailDecision
        from enforcement.networks import NetworkRegistry
        from enforcement.router import ExecutionRouter

        private_path = Path(self.tmp.name) / "issuer.key"
        public_path = Path(self.tmp.name) / "issuer.pub"
        generate_keypair(private_path, public_path)
        snapshot = self.service.snapshot(
            self.capability.agent_id,
            self.capability.capability_id,
        )
        decision = GuardrailDecision(
            self.action.intent_id,
            self.action.agent_id,
            Decision.ALLOW,
            (),
        )
        authorization = AuthorizationService().issue(
            self.action,
            decision,
            "e" * 64,
            load_private_key(private_path),
            capability=self.capability,
            authority=snapshot,
        )["execution_authorization"]
        router = ExecutionRouter(
            NetworkRegistry(),
            self.storage,
            load_public_key(public_path),
            private_key=load_private_key(private_path),
        )
        submitted = router.execute_with_receipt(
            authorization,
            lambda _action: {"tx_hash": "tx-dynamic-001"},
        )
        self.assertEqual(submitted.payload["status"], "SUBMITTED")
        self.assertEqual(
            self.storage.authority_events(
                agent_id=self.capability.agent_id,
                capability_id=self.capability.capability_id,
            ),
            [],
        )
        confirmed = router.confirm_execution_receipt(
            submitted.as_dict(),
            {"state": "CONFIRMED", "transaction_ref": "tx-dynamic-001"},
        )
        self.assertIsNotNone(confirmed)
        events = self.storage.authority_events(
            agent_id=self.capability.agent_id,
            capability_id=self.capability.capability_id,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_type"], "EXECUTION_CONFIRMED")
        self.assertEqual(events[0]["evidence_ref"], submitted.payload["receipt_id"])



if __name__ == "__main__":
    unittest.main()
