import base64
import base64
import hashlib
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient

from api import main
from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authority import CapabilityDelegationService, sign_delegation
from core.evidence import EvidenceGraph
from core.governance import (
    GovernanceMember,
    GovernancePolicy,
    sign_governance_approval,
)
from core.policy_version import create_policy_change_action
from core.identity import sign_action_intent
from core.models import ActionIntent, AgentIdentity, Capability
from core.outcome import (
    OutcomeAttestationService,
    build_outcome_attestation,
    build_outcome_claim,
)
from core.storage import Storage
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter
from enforcement.tool import ToolExecutionAdapter


class EvidenceGraphTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.private = root / "issuer.key"
        self.public = root / "issuer.pub"
        self.db = root / "audit.db"
        generate_keypair(self.private, self.public)
        self.storage = Storage(self.db)
        self.private_key = load_private_key(self.private)
        self.public_key = load_public_key(self.public)

    def tearDown(self):
        self.storage.close()
        self.tmpdir.cleanup()

    def _identity_and_capability(self):
        agent_key = Ed25519PrivateKey.generate()
        raw = agent_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        identity_id = hashlib.sha256(raw).hexdigest()
        identity = AgentIdentity(
            agent_id="evidence-agent",
            public_key_b64=base64.b64encode(raw).decode("ascii"),
            key_id=identity_id,
        )
        self.storage.register_identity(identity)
        capability = Capability(
            capability_id="cap-evidence",
            agent_id=identity.agent_id,
            identity_id=identity_id,
            allowed_actions=("mcp.tool.call",),
            allowed_targets=("github.create_issue",),
        )
        self.storage.register_capability(capability)
        return agent_key, identity, capability

    def test_graph_proves_identity_policy_capability_and_execution(self):
        agent_key, identity, capability = self._identity_and_capability()
        from core.engine import GuardrailEngine
        from core.policy import Policy

        policy_path = Path(self.tmpdir.name) / "policy.yaml"
        policy_path.write_text(
            "allowed_action_types: [mcp.tool.call]\n"
            "allowed_targets: [github.create_issue]\n",
            encoding="utf-8",
        )
        engine = GuardrailEngine(
            Policy.load(policy_path),
            self.storage,
            policy_source_ref=str(policy_path),
        )
        action = ActionIntent(
            agent_id=identity.agent_id,
            action_type="mcp.tool.call",
            target="github.create_issue",
            metadata={"arguments": {"title": "evidence"}},
        )
        agent_signature = sign_action_intent(action, identity.key_id, agent_key)
        artifacts = engine.authorize_action(
            action,
            capability.capability_id,
            identity.key_id,
            agent_signature,
            self.private_key,
        )
        authorization = artifacts["execution_authorization"]
        adapter = ToolExecutionAdapter(
            self.storage,
            self.public_key,
            {"github.create_issue": lambda _action: "tool-ready"},
        )
        router = ExecutionRouter(
            NetworkRegistry(),
            self.storage,
            self.public_key,
            self.private_key,
            generic_adapters={"mcp.tool.call": adapter},
        )
        submitted = router.execute_with_receipt(
            authorization,
            lambda _action: {"transaction_hash": "effect-evidence-1"},
            executor="evidence-test",
        )
        confirmed = router.confirm_execution_receipt(
            submitted.as_dict(),
            {
                "state": "CONFIRMED",
                "transaction_ref": "effect-evidence-1",
                "block_ref": "effect-block-1",
            },
        )
        attestor_key = Ed25519PrivateKey.generate()
        raw_attestor = attestor_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        attestor_id = "evidence-external-verifier"
        outcome_service = OutcomeAttestationService(
            self.storage,
            self.public_key,
        )
        outcome_service.register_attestor(
            attestor_id=attestor_id,
            public_key_b64=base64.b64encode(raw_attestor).decode("ascii"),
            attestor_type="EXTERNAL_VERIFIER",
        )
        claim = build_outcome_claim(
            confirmed.as_dict(),
            status="SUCCEEDED",
            executor_id="evidence-test",
            evidence_kind="MCP_RESULT",
            evidence_ref="mcp-result:evidence-1",
            result_sha256=hashlib.sha256(b"tool-ready").hexdigest(),
        )
        attestation = build_outcome_attestation(
            claim,
            attestor_id=attestor_id,
            attestor_type="EXTERNAL_VERIFIER",
            private_key=attestor_key,
        )
        outcome = outcome_service.verify_and_record(attestation)
        self.assertTrue(outcome["valid"])
        graph = EvidenceGraph(self.storage, self.public_key).build(
            authorization["payload"]["authorization_id"]
        )
        node_types = {node["type"] for node in graph["nodes"]}
        self.assertIn("identity", node_types)
        self.assertIn("agent_signature", node_types)
        self.assertIn("capability", node_types)
        self.assertIn("policy_version", node_types)
        self.assertIn("execution_authorization", node_types)
        self.assertIn("execution_receipt", node_types)
        self.assertIn("outcome_claim", node_types)
        self.assertIn("outcome_attestation", node_types)
        self.assertIn("authority_event", node_types)
        self.assertTrue(
            graph["verification"]["all_signed_artifacts_valid"],
            graph["verification"],
        )
        self.assertTrue(
            graph["verification"][
                f"outcome_attestation:{attestation['payload']['attestation_id']}"
            ]["valid"]
        )
        self.assertEqual(confirmed.payload["status"], "CONFIRMED")

    def test_graph_proves_signed_delegation(self):
        root_key = Ed25519PrivateKey.generate()
        child_key = Ed25519PrivateKey.generate()
        root_raw = root_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        child_raw = child_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        root_id = hashlib.sha256(root_raw).hexdigest()
        child_id = hashlib.sha256(child_raw).hexdigest()
        root_identity = AgentIdentity(
            agent_id="delegation-root",
            public_key_b64=base64.b64encode(root_raw).decode("ascii"),
            key_id=root_id,
        )
        child_identity = AgentIdentity(
            agent_id="delegation-child",
            public_key_b64=base64.b64encode(child_raw).decode("ascii"),
            key_id=child_id,
        )
        self.storage.register_identity(root_identity)
        self.storage.register_identity(child_identity)
        root = Capability(
            capability_id="cap-delegation-root",
            agent_id=root_identity.agent_id,
            identity_id=root_id,
            allowed_actions=("mcp.tool.call",),
            allowed_targets=("github.create_issue",),
            delegation_depth=0,
        )
        child = Capability(
            capability_id="cap-delegation-child",
            agent_id=child_identity.agent_id,
            identity_id=child_id,
            delegated_from=root.capability_id,
            delegated_by_identity_id=root_id,
            delegation_depth=1,
            allowed_actions=("mcp.tool.call",),
            allowed_targets=("github.create_issue",),
        )
        self.storage.register_capability(root)
        delegation_signature = sign_delegation(
            root.capability_id,
            child,
            root_id,
            root_key,
        )
        CapabilityDelegationService(self.storage).delegate(
            root.capability_id,
            child,
            root_id,
            delegation_signature,
        )
        from core.engine import GuardrailEngine
        from core.policy import Policy
        policy_path = Path(self.tmpdir.name) / "delegation-policy.yaml"
        policy_path.write_text(
            "allowed_action_types: [mcp.tool.call]\n"
            "allowed_targets: [github.create_issue]\n",
            encoding="utf-8",
        )
        engine = GuardrailEngine(
            Policy.load(policy_path),
            self.storage,
            policy_source_ref=str(policy_path),
        )
        action = ActionIntent(
            agent_id=child_identity.agent_id,
            action_type="mcp.tool.call",
            target="github.create_issue",
            metadata={"arguments": {"title": "delegated"}},
        )
        agent_signature = sign_action_intent(action, child_id, child_key)
        artifacts = engine.authorize_action(
            action,
            child.capability_id,
            child_id,
            agent_signature,
            self.private_key,
        )
        graph = EvidenceGraph(self.storage, self.public_key).build(
            artifacts["execution_authorization"]["payload"]["authorization_id"]
        )
        self.assertIn("delegation", {node["type"] for node in graph["nodes"]})
        self.assertTrue(graph["verification"][f"delegation:{child.capability_id}"]["valid"])

    def test_graph_proves_governed_policy_publication(self):
        from core.engine import GuardrailEngine
        from core.policy import Policy
        from core.policy_version import build_policy_version, sign_policy_version

        policy_path = Path(self.tmpdir.name) / "governed-policy.yaml"
        policy_path.write_text(
            "allowed_action_types: [mcp.tool.call]\n"
            "allowed_targets: [github.create_issue]\n",
            encoding="utf-8",
        )
        policy = Policy.load(policy_path)
        engine = GuardrailEngine(
            policy,
            self.storage,
            policy_source_ref=str(policy_path),
        )
        agent_key, identity, capability = self._identity_and_capability()
        action = ActionIntent(
            agent_id=identity.agent_id,
            action_type="mcp.tool.call",
            target="github.create_issue",
        )
        agent_signature = sign_action_intent(action, identity.key_id, agent_key)
        artifacts = engine.authorize_action(
            action,
            capability.capability_id,
            identity.key_id,
            agent_signature,
            self.private_key,
        )
        signed_policy = artifacts["decision_receipt"]["payload"]["signed_policy_version"]
        governor_policy = GovernancePolicy(
            policy_id="evidence-governance",
            version=1,
            threshold=1,
            members=(GovernanceMember.from_public_key(self.public_key, "governor"),),
            allowed_actions=("POLICY_CHANGE",),
        )
        governance_action = create_policy_change_action(
            signed_policy,
            governance_policy=governor_policy,
            reason="publish policy for evidence provenance",
        )
        approval = sign_governance_approval(
            governance_action,
            role="governor",
            private_key=self.private_key,
        )
        self.storage.register_governed_policy_change(
            signed_policy,
            {
                "policy_version": signed_policy,
                "governance_action": governance_action.as_dict(),
                "approvals": [approval.as_dict()],
                "governance_policy": governor_policy.as_dict(),
                "governance_policy_sha256": governor_policy.digest,
                "algorithm": "Ed25519-POLICY-MULTIPARTY",
            },
            governance_approvals=[approval.as_dict()],
        )
        graph = EvidenceGraph(self.storage, self.public_key).build(
            artifacts["execution_authorization"]["payload"]["authorization_id"]
        )
        node_types = {node["type"] for node in graph["nodes"]}
        self.assertIn("governance_policy", node_types)
        self.assertIn("governance_action", node_types)
        self.assertIn("governance_approval", node_types)
        governance_checks = [
            value for key, value in graph["verification"].items()
            if key.startswith("governance:")
        ]
        self.assertTrue(governance_checks)
        self.assertTrue(all(item["valid"] for item in governance_checks))

    def test_api_exposes_evidence_by_authorization(self):
        root = Path(self.tmpdir.name)
        old = (main.POLICY_PATH, main.DB_PATH, main.PRIVATE_KEY_PATH, main.PUBLIC_KEY_PATH)
        main.POLICY_PATH = str(root / "api-policy.yaml")
        main.DB_PATH = str(root / "api-audit.db")
        main.PRIVATE_KEY_PATH = str(root / "api-issuer.key")
        main.PUBLIC_KEY_PATH = str(root / "api-issuer.pub")
        Path(main.POLICY_PATH).write_text("allowed_action_types: [mcp.tool.call]\n", encoding="utf-8")
        agent_key = Ed25519PrivateKey.generate()
        raw = agent_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        identity_id = hashlib.sha256(raw).hexdigest()
        identity = AgentIdentity(
            agent_id="api-evidence-agent",
            public_key_b64=base64.b64encode(raw).decode("ascii"),
            key_id=identity_id,
        )
        action = ActionIntent(
            agent_id=identity.agent_id,
            action_type="mcp.tool.call",
            target="github.create_issue",
            timestamp=1700000000.0,
            intent_id="api-evidence-intent",
        )
        capability = Capability(
            capability_id="cap-api-evidence",
            agent_id=identity.agent_id,
            identity_id=identity_id,
            allowed_actions=("mcp.tool.call",),
            allowed_targets=("github.create_issue",),
        )
        try:
            with TestClient(main.app) as client:
                main._storage.register_identity(identity)
                main._storage.register_capability(capability)
                signature = sign_action_intent(action, identity_id, agent_key)
                response = client.post("/v1/actions/authorize", json={
                    "identity_id": identity_id,
                    "capability_id": capability.capability_id,
                    "agent_id": action.agent_id,
                    "agent_signature": signature,
                    "intent_id": action.intent_id,
                    "timestamp": action.timestamp,
                    "action_type": action.action_type,
                    "target": action.target,
                })
                self.assertEqual(response.status_code, 200)
                auth_id = response.json()["execution_authorization"]["payload"]["authorization_id"]
                evidence = client.get(f"/v1/evidence/authorization/{auth_id}")
                self.assertEqual(evidence.status_code, 200)
                self.assertEqual(evidence.json()["authorization_id"], auth_id)
                self.assertTrue(evidence.json()["verification"]["decision_receipt"]["valid"])
        finally:
            if main._storage is not None:
                main._storage.close()
            main._storage = main._engine = main._policy = None
            main.POLICY_PATH, main.DB_PATH, main.PRIVATE_KEY_PATH, main.PUBLIC_KEY_PATH = old


if __name__ == "__main__":
    unittest.main()
