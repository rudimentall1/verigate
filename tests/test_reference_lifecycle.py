import base64
import hashlib
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.effect_verification import MCPToolVerifier
from core.engine import GuardrailEngine
from core.evidence import EvidenceGraph
from core.evidence_manifest import build_manifest, verify_manifest
from core.models import ActionIntent, AgentIdentity, Capability
from core.outcome import OutcomeAttestationService, build_outcome_attestation, build_outcome_claim
from core.identity import sign_action_intent
from core.policy import Policy
from core.storage import Storage
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter
from enforcement.tool import ToolExecutionAdapter


class VerigateReferenceLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.private_path, self.public_path = root / "issuer.key", root / "issuer.pub"
        generate_keypair(self.private_path, self.public_path)
        self.private_key = load_private_key(self.private_path)
        self.public_key = load_public_key(self.public_path)
        self.storage = Storage(root / "verigate.db")

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def _authorized_execution(self):
        agent_key = Ed25519PrivateKey.generate()
        raw = agent_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        identity_id = hashlib.sha256(raw).hexdigest()
        identity = AgentIdentity(
            agent_id="reference-agent",
            public_key_b64=base64.b64encode(raw).decode(),
            key_id=identity_id,
        )
        self.storage.register_identity(identity)
        capability = Capability(
            capability_id="reference-capability",
            agent_id=identity.agent_id,
            identity_id=identity_id,
            allowed_actions=("mcp.tool.call",),
            allowed_targets=("orders.create",),
        )
        self.storage.register_capability(capability)

        policy_path = Path(self.tmp.name) / "policy.yaml"
        policy_path.write_text(
            "allowed_action_types: [mcp.tool.call]\n"
            "allowed_targets: [orders.create]\n",
            encoding="utf-8",
        )
        engine = GuardrailEngine(
            Policy.load(policy_path), self.storage, policy_source_ref=str(policy_path)
        )
        action = ActionIntent(
            agent_id=identity.agent_id,
            action_type="mcp.tool.call",
            target="orders.create",
            metadata={"arguments": {"sku": "VERIGATE", "quantity": 1}},
        )
        artifacts = engine.authorize_action(
            action,
            capability.capability_id,
            identity.key_id,
            sign_action_intent(action, identity.key_id, agent_key),
            self.private_key,
        )
        authorization = artifacts["execution_authorization"]
        adapter = ToolExecutionAdapter(
            self.storage, self.public_key,
            {"orders.create": lambda _action: {"order_id": "order-1", "status": "created"}},
        )
        router = ExecutionRouter(
            NetworkRegistry(), self.storage, self.public_key, self.private_key,
            generic_adapters={"mcp.tool.call": adapter},
        )
        submitted = router.execute_with_receipt(
            authorization,
            lambda _action: {"transaction_hash": "mcp-effect-1"},
            executor="executor-reference",
        )
        receipt = router.confirm_execution_receipt(
            submitted.as_dict(),
            {"state": "CONFIRMED", "transaction_ref": "mcp-effect-1"},
            executor="executor-reference",
        )
        return authorization, receipt

    def _attestor(self):
        key = Ed25519PrivateKey.generate()
        raw = key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        OutcomeAttestationService(self.storage, self.public_key).register_attestor(
            attestor_id="external-reference",
            public_key_b64=base64.b64encode(raw).decode(),
            attestor_type="EXTERNAL_VERIFIER",
        )
        return key

    def test_reference_lifecycle_is_offline_verifiable(self):
        authorization, receipt = self._authorized_execution()
        observed = MCPToolVerifier().verify_result(
            authorization,
            tool_name="orders.create",
            result={"order_id": "order-1", "status": "created"},
            evidence_ref="mcp://orders.create/order-1",
            target_identity="orders-service",
            observed_at=100.0,
        )
        self.assertEqual(observed.effect_status, "SUCCEEDED")

        attestor_key = self._attestor()
        claim = build_outcome_claim(
            receipt.as_dict(),
            status="SUCCEEDED",
            executor_id="executor-reference",
            evidence_kind=observed.evidence_kind,
            evidence_ref=observed.evidence_ref,
            result_sha256=observed.result_sha256,
        )
        attestation = build_outcome_attestation(
            claim,
            attestor_id="external-reference",
            attestor_type="EXTERNAL_VERIFIER",
            private_key=attestor_key,
        )
        outcome = OutcomeAttestationService(
            self.storage, self.public_key
        ).verify_and_record(attestation)
        self.assertIsNotNone(outcome["authority_event"])

        graph = EvidenceGraph(self.storage, self.public_key).build(authorization["payload"]["authorization_id"])
        manifest = build_manifest(graph, self.private_key)
        result = verify_manifest(manifest, manifest["issuer_public_key_b64"])
        self.assertTrue(result["valid"])
        types = {node["type"] for node in manifest["payload"]["nodes"]}
        for required in ("execution_authorization", "execution_receipt", "outcome_attestation", "authority_event"):
            self.assertIn(required, types)

    def test_invalid_independent_outcome_cannot_update_authority(self):
        authorization, receipt = self._authorized_execution()
        attestor_key = self._attestor()
        observed = MCPToolVerifier().verify_result(
            authorization,
            tool_name="orders.create",
            result={"order_id": "order-1", "status": "created"},
            evidence_ref="mcp://orders.create/order-1",
        )
        claim = build_outcome_claim(
            receipt.as_dict(),
            status="FAILED",
            executor_id="executor-reference",
            evidence_kind=observed.evidence_kind,
            evidence_ref=observed.evidence_ref,
            result_sha256=observed.result_sha256,
        )
        attestation = build_outcome_attestation(
            claim,
            attestor_id="external-reference",
            attestor_type="EXTERNAL_VERIFIER",
            private_key=attestor_key,
        )
        with self.assertRaises(ValueError):
            OutcomeAttestationService(self.storage, self.public_key).verify_and_record(attestation)
        self.assertEqual(
            self.storage.authority_events(agent_id="reference-agent", capability_id="reference-capability"), []
        )


if __name__ == "__main__":
    unittest.main()
