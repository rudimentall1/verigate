import base64
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.engine import GuardrailEngine
from core.evidence import EvidenceGraph
from core.attestor import AttestorAuthorityService
from core.governance import GovernanceMember, GovernancePolicy, governor_id
from core.genesis_lifecycle import GenesisLifecycle
from core.identity import sign_action_intent
from core.models import ActionIntent, AgentIdentity, Capability
from core.outcome import (
    OutcomeAttestationService,
    build_outcome_attestation,
    build_outcome_claim,
)
from core.policy import Policy
from core.authority_state import AuthorityPolicy, AuthorityState, DynamicAuthorityService
from core.proof_engine import digest
from core.proof_package import serialize_proof_package, verify_proof_package
from core.storage import Storage
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter
from enforcement.tool import ToolExecutionAdapter


def _governance_approval(action, private_key):
    now = time.time()
    payload = {
        "governance_version": 1,
        "action_digest": digest(action),
        "governor_id": governor_id(private_key.public_key()),
        "role": "governor",
        "approval_id": "approval-" + action["action_id"],
        "issued_at": now,
        "expires_at": now + 300,
        "nonce": "nonce-" + action["action_id"],
    }
    return {
        "payload": payload,
        "signature": base64.b64encode(private_key.sign(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        )).decode(),
        "algorithm": "Ed25519",
    }


class GenesisLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.private_path = root / "issuer.key"
        self.public_path = root / "issuer.pub"
        generate_keypair(self.private_path, self.public_path)
        self.private = load_private_key(self.private_path)
        self.public = load_public_key(self.public_path)
        self.storage = Storage(root / "verigate.db")
        self.governance_key = Ed25519PrivateKey.generate()
        self.governance_policy = GovernancePolicy(
            policy_id="genesis-test-governance",
            version=1,
            threshold=1,
            members=(GovernanceMember.from_public_key(self.governance_key.public_key(), "governor"),),
            allowed_actions=("ATTESTOR_REGISTER",),
        )

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def test_full_genesis_lifecycle_reuses_enforcement_and_proof_boundaries(self):
        agent_key = Ed25519PrivateKey.generate()
        raw = agent_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        identity_id = hashlib.sha256(raw).hexdigest()
        self.storage.register_identity(AgentIdentity(
            agent_id="genesis-agent",
            public_key_b64=base64.b64encode(raw).decode(),
            key_id=identity_id,
        ))
        capability = Capability(
            capability_id="genesis-cap",
            agent_id="genesis-agent",
            identity_id=identity_id,
            allowed_actions=("mcp.tool.call",),
            allowed_targets=("orders.create",),
            allowed_assets=("USDC",),
            max_per_action={"USDC": 100.0},
        )
        self.storage.register_capability(capability)
        policy = Policy(raw={
            "allowed_action_types": ["mcp.tool.call"],
            "allowed_targets": ["orders.create"],
        })
        authority_service = DynamicAuthorityService(
            self.storage,
            AuthorityPolicy(probation_successes=1),
        )
        engine = GuardrailEngine(
            policy,
            self.storage,
            authority_service=authority_service,
        )

        action = ActionIntent(
            agent_id="genesis-agent",
            action_type="mcp.tool.call",
            target="orders.create",
            asset="USDC",
            amount=5.0,
            metadata={"arguments": {"sku": "VERIGATE", "quantity": 1}},
        )
        adapter = ToolExecutionAdapter(
            self.storage,
            self.public,
            {"orders.create": lambda _action: {"order_id": "order-1"}},
        )
        router = ExecutionRouter(
            NetworkRegistry(),
            self.storage,
            self.public,
            self.private,
            generic_adapters={"mcp.tool.call": adapter},
        )
        outcome_service = OutcomeAttestationService(self.storage, self.public)
        attestor_key = Ed25519PrivateKey.generate()
        attestor_raw = attestor_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        attestor_service = AttestorAuthorityService(self.storage)
        attestor_action = attestor_service.build_action(
            action="ATTESTOR_REGISTER",
            attestor_id="verifier-1",
            reason="Genesis lifecycle test attestor",
            governance_policy_sha256=self.governance_policy.digest,
            public_key_b64=base64.b64encode(attestor_raw).decode(),
            attestor_type="EXTERNAL_VERIFIER",
        )
        attestor_service.apply(
            attestor_action,
            [_governance_approval(attestor_action, self.governance_key)],
            self.governance_policy,
        )
        lifecycle = GenesisLifecycle(
            engine,
            router,
            outcome_service,
            EvidenceGraph(self.storage, self.public),
            self.private,
        )

        lifecycle.authorize(
            action,
            capability.capability_id,
            identity_id,
            sign_action_intent(action, identity_id, agent_key),
            self.private,
        )
        self.assertEqual(lifecycle.stage.value, "AUTHORIZE")
        receipt = lifecycle.execute(
            lambda _action: {"transaction_hash": "mcp-effect-1"},
            executor="executor-1",
        )
        self.assertEqual(
            receipt["payload"]["genesis_authority"],
            lifecycle.authorization["execution_authorization"]["payload"]["genesis_authority"],
        )
        self.assertEqual(
            receipt["payload"]["genesis_authority_sha256"],
            lifecycle.authorization["execution_authorization"]["payload"]["genesis_authority_sha256"],
        )
        lifecycle.confirm({
            "state": "CONFIRMED",
            "transaction_ref": "mcp-effect-1",
        })
        claim = build_outcome_claim(
            lifecycle.execution_receipt,
            status="SUCCEEDED",
            executor_id="executor-1",
            evidence_kind="EXECUTOR_RESULT",
            evidence_ref="executor-report-1",
            result_sha256=hashlib.sha256(b"order-1").hexdigest(),
        )
        attestation = build_outcome_attestation(
            claim,
            attestor_id="verifier-1",
            attestor_type="EXTERNAL_VERIFIER",
            private_key=attestor_key,
        )
        outcome = lifecycle.observe(attestation)
        self.assertTrue(outcome["valid"])
        learning = lifecycle.learn()
        self.assertTrue(learning["valid"])
        self.assertIsNotNone(learning["authority_event"])
        manifest = lifecycle.prove()
        self.assertTrue(lifecycle.result().manifest is manifest)
        self.assertEqual(lifecycle.stage.value, "PROVE")
        self.assertEqual(
            manifest["payload"]["proof_profile"],
            "authority_lifecycle",
        )
        self.assertEqual(
            learning["proof_manifest_sha256"],
            digest(manifest),
        )
        self.assertEqual(lifecycle.stage.value, "PROVE")
        self.assertEqual(
            lifecycle.result().learning["authority_snapshot"]["agent_id"],
            "genesis-agent",
        )

        package = lifecycle.package()
        package_bytes = serialize_proof_package(package)
        package_result = verify_proof_package(package_bytes)
        self.assertTrue(package_result["valid"], package_result)
        self.assertTrue(package_result["package_valid"])
        self.assertEqual(package_result["proof_profile"], "authority_lifecycle")
        self.assertEqual(package_result["node_count"], len(manifest["payload"]["nodes"]))

        learned_snapshot = lifecycle.result()["learning"]["authority_snapshot"]
        self.assertEqual(learned_snapshot["state"], AuthorityState.STANDARD.value)
        self.assertEqual(learned_snapshot["multiplier"], 0.50)
        self.assertLessEqual(learned_snapshot["multiplier"], 1.0)
        self.assertEqual(capability.digest, self.storage.capability(capability.capability_id).digest)

        next_action = ActionIntent(
            agent_id="genesis-agent",
            action_type="mcp.tool.call",
            target="orders.create",
            asset="USDC",
            amount=20.0,
            metadata={"arguments": {"sku": "VERIGATE-NEXT", "quantity": 1}},
        )
        next_artifacts = engine.authorize_action(
            next_action,
            capability.capability_id,
            identity_id,
            sign_action_intent(next_action, identity_id, agent_key),
            self.private,
        )
        next_authorization = next_artifacts["execution_authorization"]
        self.assertIsNotNone(next_authorization)
        self.assertEqual(
            next_authorization["payload"]["authority_state"]["state"],
            AuthorityState.STANDARD.value,
        )
        self.assertEqual(
            next_authorization["payload"]["authority_multiplier"],
            0.50,
        )
        self.assertEqual(
            next_authorization["payload"]["capability_sha256"],
            capability.digest,
        )

        authority_service.record_event(
            agent_id="genesis-agent",
            capability_id=capability.capability_id,
            identity_id=identity_id,
            event_type="EXECUTION_FAILED",
            evidence_ref="post-package-mutation",
            metadata={"reason": "package independence regression"},
        )
        package_after_mutation = verify_proof_package(package_bytes)
        self.assertTrue(package_after_mutation["valid"], package_after_mutation)
        self.assertEqual(
            package_after_mutation["checks"]["historical_authority"]["details"]["ledger_sequence"],
            package_result["checks"]["historical_authority"]["details"]["ledger_sequence"],
        )
        types = {node["type"] for node in manifest["payload"]["nodes"]}
        self.assertIn("execution_authorization", types)
        self.assertIn("execution_receipt", types)
        self.assertIn("outcome_attestation", types)

    def test_lifecycle_cannot_execute_without_executable_authorization(self):
        agent_key = Ed25519PrivateKey.generate()
        raw = agent_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        identity_id = hashlib.sha256(raw).hexdigest()
        self.storage.register_identity(AgentIdentity(
            agent_id="blocked-agent",
            public_key_b64=base64.b64encode(raw).decode(),
            key_id=identity_id,
        ))
        capability = Capability(
            capability_id="blocked-cap",
            agent_id="blocked-agent",
            identity_id=identity_id,
            allowed_actions=("mcp.tool.call",),
            allowed_targets=("blocked.target",),
        )
        self.storage.register_capability(capability)
        engine = GuardrailEngine(Policy(
            allowed_action_types=["other.action"],
            allowed_targets=["other.target"],
            raw={
                "allowed_action_types": ["other.action"],
                "allowed_targets": ["other.target"],
            },
        ), self.storage)
        action = ActionIntent(
            agent_id="blocked-agent",
            action_type="mcp.tool.call",
            target="blocked.target",
        )
        lifecycle = GenesisLifecycle(
            engine,
            ExecutionRouter(NetworkRegistry(), self.storage, self.public, self.private),
            OutcomeAttestationService(self.storage, self.public),
            EvidenceGraph(self.storage, self.public),
            self.private,
        )
        artifacts = lifecycle.authorize(
            action,
            capability.capability_id,
            identity_id,
            sign_action_intent(action, identity_id, agent_key),
            self.private,
        )
        self.assertIsNone(artifacts["execution_authorization"])
        with self.assertRaises(PermissionError):
            lifecycle.execute(lambda _action: {"transaction_hash": "must-not-run"})

if __name__ == "__main__":
    unittest.main()
