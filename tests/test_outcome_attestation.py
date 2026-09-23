import base64
import hashlib
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.engine import GuardrailEngine
from core.models import ActionIntent, AgentIdentity, Capability
from core.outcome import (
    OutcomeAttestationService,
    build_outcome_attestation,
    build_outcome_claim,
)
from core.policy import Policy
from core.identity import sign_action_intent
from core.storage import Storage
from enforcement.router import ExecutionRouter
from enforcement.networks import NetworkRegistry
from enforcement.tool import ToolExecutionAdapter


class OutcomeAttestationTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.private_path = root / "issuer.key"
        self.public_path = root / "issuer.pub"
        self.db_path = root / "outcome.db"
        generate_keypair(self.private_path, self.public_path)
        self.private_key = load_private_key(self.private_path)
        self.public_key = load_public_key(self.public_path)
        self.storage = Storage(self.db_path)

    def tearDown(self):
        self.storage.close()
        self.tmpdir.cleanup()

    def _confirmed_execution(self):
        agent_key = Ed25519PrivateKey.generate()
        raw = agent_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        identity_id = hashlib.sha256(raw).hexdigest()
        identity = AgentIdentity(
            agent_id="outcome-agent",
            public_key_b64=base64.b64encode(raw).decode("ascii"),
            key_id=identity_id,
        )
        self.storage.register_identity(identity)
        capability = Capability(
            capability_id="cap-outcome",
            agent_id=identity.agent_id,
            identity_id=identity_id,
            allowed_actions=("mcp.tool.call",),
            allowed_targets=("github.create_issue",),
        )
        self.storage.register_capability(capability)

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
            metadata={"arguments": {"title": "outcome"}},
        )
        signature = sign_action_intent(action, identity_id, agent_key)
        artifacts = engine.authorize_action(
            action,
            capability.capability_id,
            identity_id,
            signature,
            self.private_key,
        )
        authorization = artifacts["execution_authorization"]

        adapter = ToolExecutionAdapter(
            self.storage,
            self.public_key,
            {"github.create_issue": lambda _action: "ready"},
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
            lambda _action: {"transaction_hash": "outcome-effect"},
            executor="executor-1",
        )
        confirmed = router.confirm_execution_receipt(
            submitted.as_dict(),
            {
                "state": "CONFIRMED",
                "transaction_ref": "outcome-effect",
                "block_ref": "external-check",
            },
            executor="executor-1",
        )
        return authorization, confirmed

    def _register(self, service, attestor_id, attestor_type):
        key = Ed25519PrivateKey.generate()
        raw = key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        service.register_attestor(
            attestor_id=attestor_id,
            public_key_b64=base64.b64encode(raw).decode("ascii"),
            attestor_type=attestor_type,
        )
        return key

    def test_self_report_is_stored_but_does_not_change_authority(self):
        _authorization, receipt = self._confirmed_execution()
        service = OutcomeAttestationService(self.storage, self.public_key)
        key = self._register(service, "executor-1", "EXECUTOR")
        claim = build_outcome_claim(
            receipt.as_dict(),
            status="SUCCEEDED",
            executor_id="executor-1",
            evidence_kind="EXECUTOR_RESULT",
            evidence_ref="executor-report-1",
            result_sha256=hashlib.sha256(b"ready").hexdigest(),
        )
        attestation = build_outcome_attestation(
            claim,
            attestor_id="executor-1",
            attestor_type="EXECUTOR_SELF_REPORT",
            private_key=key,
        )
        result = service.verify_and_record(attestation)
        self.assertTrue(result["valid"])
        self.assertIsNone(result["authority_event"])
        self.assertEqual(self.storage.authority_events(
            agent_id="outcome-agent",
            capability_id="cap-outcome",
        ), [])

    def test_external_attestation_changes_authority_and_is_evidence(self):
        authorization, receipt = self._confirmed_execution()
        service = OutcomeAttestationService(self.storage, self.public_key)
        key = self._register(service, "external-verifier-1", "EXTERNAL_VERIFIER")
        claim = build_outcome_claim(
            receipt.as_dict(),
            status="SUCCEEDED",
            executor_id="executor-1",
            evidence_kind="MCP_RESULT",
            evidence_ref="mcp-verifier-result-1",
            result_sha256=hashlib.sha256(b"verified").hexdigest(),
        )
        attestation = build_outcome_attestation(
            claim,
            attestor_id="external-verifier-1",
            attestor_type="EXTERNAL_VERIFIER",
            private_key=key,
        )
        result = service.verify_and_record(attestation)
        self.assertTrue(result["valid"])
        self.assertIsNotNone(result["authority_event"])
        events = self.storage.authority_events(
            agent_id="outcome-agent",
            capability_id="cap-outcome",
        )
        self.assertEqual(events[-1]["event_type"], "EXECUTION_CONFIRMED")
        self.assertEqual(events[-1]["evidence_ref"], claim["claim_id"])
        self.assertEqual(
            result["claim_sha256"],
            hashlib.sha256(
                __import__("json").dumps(
                    claim,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest(),
        )
        claims = self.storage.outcome_claims_by_authorization(
            authorization["payload"]["authorization_id"]
        )
        self.assertEqual(len(claims), 1)

    def test_tampered_attestation_is_rejected_before_persistence(self):
        _authorization, receipt = self._confirmed_execution()
        service = OutcomeAttestationService(self.storage, self.public_key)
        key = self._register(service, "external-verifier-2", "EXTERNAL_VERIFIER")
        claim = build_outcome_claim(
            receipt.as_dict(),
            status="SUCCEEDED",
            executor_id="executor-1",
            evidence_kind="HTTP_RESPONSE",
            evidence_ref="https://example.test/result/1",
            result_sha256=hashlib.sha256(b"ok").hexdigest(),
        )
        attestation = build_outcome_attestation(
            claim,
            attestor_id="external-verifier-2",
            attestor_type="EXTERNAL_VERIFIER",
            private_key=key,
        )
        attestation["payload"]["claim"]["result_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            service.verify_and_record(attestation)
        self.assertEqual(self.storage.outcome_claims_by_authorization(
            receipt.payload["authorization_id"]
        ), [])
