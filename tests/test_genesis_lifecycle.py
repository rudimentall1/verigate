import base64
import hashlib
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.engine import GuardrailEngine
from core.evidence import EvidenceGraph
from core.genesis_lifecycle import GenesisLifecycle
from core.identity import sign_action_intent
from core.models import ActionIntent, AgentIdentity, Capability
from core.outcome import (
    OutcomeAttestationService,
    build_outcome_attestation,
    build_outcome_claim,
)
from core.policy import Policy
from core.storage import Storage
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter
from enforcement.tool import ToolExecutionAdapter


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
        )
        self.storage.register_capability(capability)
        policy = Policy(raw={
            "allowed_action_types": ["mcp.tool.call"],
            "allowed_targets": ["orders.create"],
        })
        engine = GuardrailEngine(policy, self.storage)

        action = ActionIntent(
            agent_id="genesis-agent",
            action_type="mcp.tool.call",
            target="orders.create",
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
        outcome_service.register_attestor(
            attestor_id="executor-1",
            public_key_b64=base64.b64encode(attestor_raw).decode(),
            attestor_type="EXECUTOR",
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
            attestor_id="executor-1",
            attestor_type="EXECUTOR_SELF_REPORT",
            private_key=attestor_key,
        )
        outcome = lifecycle.observe(attestation)
        self.assertTrue(outcome["valid"])
        manifest = lifecycle.prove()
        self.assertTrue(lifecycle.result().manifest is manifest)
        self.assertEqual(lifecycle.stage.value, "LEARN")
        self.assertEqual(
            manifest["payload"]["proof_profile"],
            "integrity",
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
