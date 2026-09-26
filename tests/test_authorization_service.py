import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.receipt import verify_execution_authorization, verify_receipt
from core.authorization import AuthorizationService
from core.models import ActionIntent, Capability, Decision, GuardrailDecision
from core.authority_state import DynamicAuthorityService
from core.authority_intent_graph import AuthorityAwareIntentGraph, PlanAuthorityStatus
from core.authority_protocol import Authority, AuthorityState
from core.intent_graph import IntentGraphBuilder
from core.policy import Policy
from core.storage import Storage


class AuthorizationServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.priv = Path(self.tmpdir.name) / "issuer.key"
        self.pub = Path(self.tmpdir.name) / "issuer.pub"
        generate_keypair(self.priv, self.pub)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _action(self):
        return ActionIntent(
            agent_id="agent-rwa",
            action_type="evm.transaction",
            target="0xasset",
            resource="chain:8453",
            metadata={"evm_transaction": {"chain_id": 8453, "to": "0xasset", "value_wei": 0, "data": "0x"}},
        )

    def test_generic_action_is_decision_only_without_authority(self):
        action = self._action()
        decision = GuardrailDecision(action.intent_id, action.agent_id, Decision.ALLOW, ())
        artifacts = AuthorizationService().issue_decision_receipt(
            action, decision, "a" * 64, load_private_key(self.priv)
        )
        receipt = artifacts["decision_receipt"]
        self.assertTrue(verify_receipt(receipt, load_public_key(self.pub))[0])
        self.assertIsNone(artifacts["execution_authorization"])

    def test_warn_never_mints_execution_capability(self):
        action = self._action()
        decision = GuardrailDecision(action.intent_id, action.agent_id, Decision.WARN, ())
        artifacts = AuthorizationService().issue(
            action, decision, "b" * 64, load_private_key(self.priv)
        )
        self.assertIsNone(artifacts["execution_authorization"])

    def test_capability_scope_is_bound_to_execution_authorization(self):
        action = self._action()
        capability = Capability(
            capability_id="cap-rwa-001",
            agent_id=action.agent_id,
            allowed_actions=("evm.transaction",),
            allowed_targets=(action.target,),
        )
        storage = Storage(Path(self.tmpdir.name) / "authority.db")
        policy = Policy(
            allowed_action_types=["evm.transaction"],
            allowed_targets=["0xasset"],
            raw={
                "allowed_action_types": ["evm.transaction"],
                "allowed_targets": ["0xasset"],
            },
        )
        snapshot = DynamicAuthorityService(storage).snapshot(
            action.agent_id, capability.capability_id
        )
        decision = GuardrailDecision(action.intent_id, action.agent_id, Decision.ALLOW, ())
        artifacts = AuthorizationService().issue(
            action,
            decision,
            policy.digest,
            load_private_key(self.priv),
            capability=capability,
            authority=snapshot,
            policy=policy,
        )
        storage.close()
        execution = artifacts["execution_authorization"]
        self.assertEqual(execution["payload"]["capability_id"], capability.capability_id)
        self.assertEqual(execution["payload"]["capability_version"], capability.version)
        self.assertEqual(execution["payload"]["capability_sha256"], capability.digest)
        self.assertTrue(verify_execution_authorization(execution, load_public_key(self.pub))[0])

    def test_authority_assessment_is_bound_into_execution_authorization(self):
        action = self._action()
        capability = Capability(
            capability_id="cap-rwa-001",
            agent_id=action.agent_id,
            allowed_actions=("evm.transaction",),
            allowed_targets=(action.target,),
        )
        canonical_authority = Authority(
            authority_id="auth-1",
            agent_id=action.agent_id,
            identity_id="identity-1",
            capability_id=capability.capability_id,
            capability_version=capability.version,
            capability_sha256=capability.digest,
            state=AuthorityState.STANDARD,
            multiplier=1.0,
            effective_from=1000.0,
        )
        graph = IntentGraphBuilder("plan-1").add_action(action).build()
        assessment = AuthorityAwareIntentGraph(
            graph, canonical_authority, capability
        ).assess(action.intent_id)
        self.assertEqual(assessment.status, PlanAuthorityStatus.ELIGIBLE)

        storage = Storage(Path(self.tmpdir.name) / "authority.db")
        policy = Policy(
            allowed_action_types=["evm.transaction"],
            allowed_targets=["0xasset"],
            raw={
                "allowed_action_types": ["evm.transaction"],
                "allowed_targets": ["0xasset"],
            },
        )
        snapshot = DynamicAuthorityService(storage).snapshot(
            action.agent_id, capability.capability_id
        )
        decision = GuardrailDecision(action.intent_id, action.agent_id, Decision.ALLOW, ())
        artifacts = AuthorizationService().issue(
            action,
            decision,
            policy.digest,
            load_private_key(self.priv),
            capability=capability,
            authority=snapshot,
            policy=policy,
            authority_assessment=assessment,
        )
        storage.close()

        execution = artifacts["execution_authorization"]
        genesis_binding = execution["payload"]["genesis_authority"]
        self.assertEqual(genesis_binding["intent_graph_digest"], graph.digest)
        self.assertEqual(genesis_binding["intent_graph_node_id"], action.intent_id)
        self.assertEqual(genesis_binding["authority_assessment_digest"], assessment.digest)
        self.assertEqual(genesis_binding["authority_digest"], assessment.authority_digest)
        self.assertTrue(verify_execution_authorization(execution, load_public_key(self.pub))[0])

    def test_blocked_authority_assessment_cannot_mint_execution_authorization(self):
        action = self._action()
        capability = Capability(
            capability_id="cap-rwa-001",
            agent_id=action.agent_id,
            allowed_actions=("payment",),
        )
        canonical_authority = Authority(
            authority_id="auth-1",
            agent_id=action.agent_id,
            identity_id="identity-1",
            capability_id=capability.capability_id,
            capability_version=capability.version,
            capability_sha256=capability.digest,
            state=AuthorityState.STANDARD,
            multiplier=1.0,
            effective_from=1000.0,
        )
        graph = IntentGraphBuilder("plan-1").add_action(action).build()
        assessment = AuthorityAwareIntentGraph(
            graph, canonical_authority, capability
        ).assess(action.intent_id)
        self.assertEqual(assessment.status, PlanAuthorityStatus.BLOCKED)

        decision = GuardrailDecision(action.intent_id, action.agent_id, Decision.ALLOW, ())
        with self.assertRaises(PermissionError):
            AuthorizationService().issue(
                action,
                decision,
                "a" * 64,
                load_private_key(self.priv),
                authority_assessment=assessment,
            )

    def test_capability_mismatch_cannot_mint_execution_authorization(self):
        action = self._action()
        capability = Capability(
            capability_id="cap-wrong-agent",
            agent_id="another-agent",
            allowed_actions=("evm.transaction",),
        )
        decision = GuardrailDecision(action.intent_id, action.agent_id, Decision.ALLOW, ())
        with self.assertRaises(PermissionError):
            AuthorizationService().issue(
                action, decision, "d" * 64, load_private_key(self.priv), capability=capability
            )

    def test_authority_snapshot_cannot_bind_to_different_capability(self):
        action = self._action()
        storage = Storage(Path(self.tmpdir.name) / "authority-binding.db")
        cap_a = Capability(
            capability_id="cap-authority-a",
            agent_id=action.agent_id,
            allowed_actions=("evm.transaction",),
            allowed_targets=(action.target,),
            max_per_action={"USDC": 100.0},
        )
        cap_b = Capability(
            capability_id="cap-authority-b",
            agent_id=action.agent_id,
            allowed_actions=("evm.transaction",),
            allowed_targets=(action.target,),
            max_per_action={"USDC": 100.0},
        )
        storage.register_capability(cap_a)
        storage.register_capability(cap_b)
        authority_b = DynamicAuthorityService(storage).snapshot(
            action.agent_id, cap_b.capability_id
        )
        decision = GuardrailDecision(action.intent_id, action.agent_id, Decision.ALLOW, ())

        with self.assertRaisesRegex(PermissionError, "authority capability mismatch"):
            AuthorizationService().issue(
                action,
                decision,
                "a" * 64,
                load_private_key(self.priv),
                capability=cap_a,
                authority=authority_b,
                authority_policy=DynamicAuthorityService(storage).policy,
                policy=Policy(),
            )
        storage.close()

    def test_authority_snapshot_cannot_claim_wrong_multiplier(self):
        action = self._action()
        storage = Storage(Path(self.tmpdir.name) / "authority-state.db")
        capability = Capability(
            capability_id="cap-authority-state",
            agent_id=action.agent_id,
            allowed_actions=("evm.transaction",),
            allowed_targets=(action.target,),
        )
        storage.register_capability(capability)
        service = DynamicAuthorityService(storage)
        snapshot = service.snapshot(action.agent_id, capability.capability_id)
        forged = type(snapshot)(
            agent_id=snapshot.agent_id,
            capability_id=snapshot.capability_id,
            state=snapshot.state,
            successes=snapshot.successes,
            adverse_events=snapshot.adverse_events,
            critical_events=snapshot.critical_events,
            multiplier=1.0,
            evaluated_at=snapshot.evaluated_at,
            reason=snapshot.reason,
            ledger_head_hash=snapshot.ledger_head_hash,
            authority_policy_sha256=snapshot.authority_policy_sha256,
            history_start_at=snapshot.history_start_at,
        )
        decision = GuardrailDecision(action.intent_id, action.agent_id, Decision.ALLOW, ())

        with self.assertRaisesRegex(PermissionError, "authority multiplier"):
            AuthorizationService().issue(
                action,
                decision,
                "a" * 64,
                load_private_key(self.priv),
                capability=capability,
                authority=forged,
                authority_policy=service.policy,
                policy=Policy(),
            )
        storage.close()

    def test_requested_capability_cannot_mismatch_supplied_capability(self):
        action = ActionIntent(
            agent_id="agent-rwa",
            action_type="evm.transaction",
            target="0xasset",
            requested_capability="cap-requested",
        )
        capability = Capability(
            capability_id="cap-actual",
            agent_id=action.agent_id,
            allowed_actions=("evm.transaction",),
            allowed_targets=(action.target,),
        )
        decision = GuardrailDecision(action.intent_id, action.agent_id, Decision.ALLOW, ())
        with self.assertRaisesRegex(PermissionError, "requested capability does not match"):
            AuthorizationService().issue(
                action,
                decision,
                "e" * 64,
                load_private_key(self.priv),
                capability=capability,
            )


    def test_direct_registry_registration_cannot_bypass_delegation_validation(self):
        from core.capabilities import CapabilityRegistry

        storage = Storage(Path(self.tmpdir.name) / "delegation-register.db")
        registry = CapabilityRegistry(storage)
        parent = Capability(
            capability_id="cap-parent",
            agent_id="agent-rwa",
            allowed_actions=("evm.transaction",),
        )
        child = Capability(
            capability_id="cap-child",
            agent_id="agent-rwa",
            delegated_from=parent.capability_id,
            allowed_actions=("cloud.delete",),
        )
        registry.register(parent)
        with self.assertRaisesRegex(PermissionError, "CapabilityDelegationService"):
            registry.register(child)
        storage.close()

    def test_delegated_capability_requires_registry_backed_chain(self):
        from core.capabilities import CapabilityRegistry

        action = self._action()
        storage = Storage(Path(self.tmpdir.name) / "delegation.db")
        registry = CapabilityRegistry(storage)
        parent = Capability(
            capability_id="cap-parent",
            agent_id="agent-rwa",
            allowed_actions=("evm.transaction",),
            allowed_targets=(action.target,),
        )
        child = Capability(
            capability_id="cap-child",
            agent_id="agent-rwa",
            delegated_from=parent.capability_id,
            allowed_actions=("evm.transaction",),
            allowed_targets=(action.target,),
        )
        registry.register(parent)
        storage.register_delegated_capability(child, parent.capability_id)
        decision = GuardrailDecision(action.intent_id, action.agent_id, Decision.ALLOW, ())

        with self.assertRaisesRegex(PermissionError, "registry-backed authority-chain"):
            AuthorizationService().issue(
                action,
                decision,
                "f" * 64,
                load_private_key(self.priv),
                capability=child,
                authority=DynamicAuthorityService(storage).snapshot(
                    action.agent_id, child.capability_id
                ),
                policy=Policy(),
            )
        storage.close()

    def test_parent_revocation_blocks_new_delegated_authorization(self):
        from core.capabilities import CapabilityRegistry

        action = self._action()
        storage = Storage(Path(self.tmpdir.name) / "delegation-revocation.db")
        registry = CapabilityRegistry(storage)
        parent = Capability(
            capability_id="cap-parent",
            agent_id="agent-rwa",
            allowed_actions=("evm.transaction",),
            allowed_targets=(action.target,),
        )
        child = Capability(
            capability_id="cap-child",
            agent_id="agent-rwa",
            delegated_from=parent.capability_id,
            allowed_actions=("evm.transaction",),
            allowed_targets=(action.target,),
        )
        registry.register(parent)
        storage.register_delegated_capability(child, parent.capability_id)
        registry.revoke(parent.capability_id)
        decision = GuardrailDecision(action.intent_id, action.agent_id, Decision.ALLOW, ())

        with self.assertRaisesRegex(PermissionError, "ineffective authority chain"):
            AuthorizationService().issue(
                action,
                decision,
                "f" * 64,
                load_private_key(self.priv),
                capability=child,
                capability_registry=registry,
                authority=DynamicAuthorityService(storage).snapshot(
                    action.agent_id, child.capability_id
                ),
                policy=Policy(),
            )
        storage.close()

if __name__ == "__main__":
    unittest.main()


class TestConstraintBinding(unittest.TestCase):
    def test_execution_authorization_binds_constraints(self):
        from attest.receipt import issue_execution_authorization, sign_receipt, verify_execution_authorization
        from core.models import ActionIntent, Decision, GuardrailDecision
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        key = Ed25519PrivateKey.generate()
        action = ActionIntent(agent_id="agent", action_type="api.request", target="orders", constraints={"max_amount": 10})
        decision = GuardrailDecision(action.intent_id, action.agent_id, Decision.ALLOW, ())
        receipt = sign_receipt(action, decision, "a" * 64, key)
        auth = issue_execution_authorization(receipt, key, nonce="n")
        self.assertIn("constraints_sha256", auth.payload)
        tampered = dict(auth.payload); tampered["action"] = dict(tampered["action"]); tampered["action"]["constraints"] = {"max_amount": 100}
        self.assertFalse(verify_execution_authorization({"payload": tampered, "signature": auth.signature, "algorithm": auth.algorithm}, key.public_key())[0])
