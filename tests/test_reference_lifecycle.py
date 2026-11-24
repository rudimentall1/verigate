import base64
import hashlib
import json
import time
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.effect_verification import MCPToolVerifier
from core.attestor import AttestorAuthorityService
from core.authority_state import DynamicAuthorityService
from core.engine import GuardrailEngine
from core.evidence import EvidenceGraph
from core.governance import GovernanceMember, GovernancePolicy, governor_id
from core.evidence_manifest import build_manifest, verify_manifest, canonical, graph_root
from core.offline_verifier import verify_proof
from core.proof_package import build_proof_package, serialize_proof_package
from core.models import ActionIntent, AgentIdentity, Capability
from core.outcome import OutcomeAttestationService, build_outcome_attestation, build_outcome_claim
from core.identity import sign_action_intent
from core.policy import Policy
from core.storage import Storage
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter
from enforcement.tool import ToolExecutionAdapter


def _governance_approval(action, private_key):
    payload = {
        "governance_version": 1,
        "action_digest": hashlib.sha256(
            json.dumps(action, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest(),
        "governor_id": governor_id(private_key.public_key()),
        "role": "governor",
        "approval_id": "approval-" + action["action_id"],
        "issued_at": time.time(),
        "expires_at": time.time() + 120,
        "nonce": "nonce-" + action["action_id"],
    }
    return {
        "payload": payload,
        "signature": base64.b64encode(
            private_key.sign(
                json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
            )
        ).decode(),
        "algorithm": "Ed25519",
    }


class VerigateReferenceLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.private_path, self.public_path = root / "issuer.key", root / "issuer.pub"
        generate_keypair(self.private_path, self.public_path)
        self.private_key = load_private_key(self.private_path)
        self.public_key = load_public_key(self.public_path)
        self.storage = Storage(root / "verigate.db")
        self.governance_key = Ed25519PrivateKey.generate()
        self.governance_policy = GovernancePolicy(
            policy_id="reference-governance",
            version=1,
            threshold=1,
            members=(
                GovernanceMember.from_public_key(
                    self.governance_key.public_key(), "governor"
                ),
            ),
            allowed_actions=(
                "ATTESTOR_REGISTER",
                "ATTESTOR_ACTIVATE",
                "ATTESTOR_ROTATE",
                "ATTESTOR_REVOKE",
                "ATTESTOR_EXPIRE",
            ),
        )

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def _authorized_execution(self, policy_source_ref=None):
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
            Policy.load(policy_path), self.storage, policy_source_ref=policy_source_ref or str(policy_path)
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
        genesis_binding = authorization["payload"]["genesis_authority"]
        self.assertTrue(genesis_binding["intent_graph_digest"])
        self.assertEqual(genesis_binding["intent_graph_node_id"], action.intent_id)
        self.assertTrue(genesis_binding["authority_assessment_digest"])
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
        service = AttestorAuthorityService(self.storage)
        action = service.build_action(
            action="ATTESTOR_REGISTER",
            attestor_id="external-reference",
            reason="reference lifecycle verifier",
            governance_policy_sha256=self.governance_policy.digest,
            public_key_b64=base64.b64encode(raw).decode(),
            attestor_type="EXTERNAL_VERIFIER",
        )
        service.apply(
            action,
            [_governance_approval(action, self.governance_key)],
            self.governance_policy,
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
            observed_effect=observed.as_dict(),
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

        authority_snapshot = DynamicAuthorityService(self.storage).snapshot(
            "reference-agent", "reference-capability"
        ).as_dict()
        event = self.storage.authority_events(
            agent_id="reference-agent", capability_id="reference-capability"
        )[-1]
        authority_snapshot["source_event_id"] = event["event_id"]
        graph = EvidenceGraph(self.storage, self.public_key).build(
            authorization["payload"]["authorization_id"],
            authority_snapshot_after=authority_snapshot,
        )
        manifest = build_manifest(graph, self.private_key, proof_profile="authority_lifecycle")
        result = verify_manifest(manifest, manifest["issuer_public_key_b64"])
        self.assertTrue(result["valid"])
        types = {node["type"] for node in manifest["payload"]["nodes"]}
        for required in (
            "execution_authorization",
            "execution_receipt",
            "outcome_attestation",
            "attestor_authority",
            "governance_action",
            "governance_approval",
            "authority_event",
        ):
            self.assertIn(required, types)
        self.assertTrue(graph["verification"]["all_signed_artifacts_valid"])

    def test_authority_protocol_is_verified_without_package_envelope(self):
        authorization, receipt = self._authorized_execution()
        observed = MCPToolVerifier().verify_result(
            authorization, tool_name="orders.create",
            result={"order_id": "order-1", "status": "created"},
            evidence_ref="mcp://orders.create/order-1",
        )
        attestor_key = self._attestor()
        claim = build_outcome_claim(receipt.as_dict(), status="SUCCEEDED", executor_id="executor-reference", evidence_kind=observed.evidence_kind, evidence_ref=observed.evidence_ref, result_sha256=observed.result_sha256, observed_effect=observed.as_dict())
        attestation = build_outcome_attestation(claim, attestor_id="external-reference", attestor_type="EXTERNAL_VERIFIER", private_key=attestor_key)
        OutcomeAttestationService(self.storage, self.public_key).verify_and_record(attestation)
        snapshot = DynamicAuthorityService(self.storage).snapshot("reference-agent", "reference-capability").as_dict()
        event = self.storage.authority_events(agent_id="reference-agent", capability_id="reference-capability")[-1]
        snapshot["source_event_id"] = event["event_id"]
        graph = EvidenceGraph(self.storage, self.public_key).build(authorization["payload"]["authorization_id"], authority_snapshot_after=snapshot)
        manifest = build_manifest(graph, self.private_key, proof_profile="authority_lifecycle")
        result = verify_proof(manifest, trusted_public_key_b64=manifest["issuer_public_key_b64"])
        self.assertTrue(result["valid"], result)
        self.assertTrue(result["checks"]["authority_protocol"]["valid"])
        self.assertEqual(result["checks"]["authority_protocol"]["details"]["assertion_count"], 9)

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
            observed_effect=observed.as_dict(),
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


    def _valid_manifest(self, policy_source_ref=None):
        authorization, receipt = self._authorized_execution(policy_source_ref=policy_source_ref)
        observed = MCPToolVerifier().verify_result(
            authorization,
            tool_name="orders.create",
            result={"order_id": "order-1", "status": "created"},
            evidence_ref="mcp://orders.create/order-1",
            target_identity="orders-service",
        )
        attestor_key = self._attestor()
        claim = build_outcome_claim(
            receipt.as_dict(),
            status="SUCCEEDED",
            executor_id="executor-reference",
            evidence_kind=observed.evidence_kind,
            evidence_ref=observed.evidence_ref,
            result_sha256=observed.result_sha256,
            observed_effect=observed.as_dict(),
        )
        attestation = build_outcome_attestation(
            claim,
            attestor_id="external-reference",
            attestor_type="EXTERNAL_VERIFIER",
            private_key=attestor_key,
        )
        OutcomeAttestationService(self.storage, self.public_key).verify_and_record(attestation)
        authority_snapshot = DynamicAuthorityService(self.storage).snapshot(
            "reference-agent", "reference-capability"
        ).as_dict()
        event = self.storage.authority_events(
            agent_id="reference-agent", capability_id="reference-capability"
        )[-1]
        authority_snapshot["source_event_id"] = event["event_id"]
        graph = EvidenceGraph(self.storage, self.public_key).build(
            authorization["payload"]["authorization_id"],
            authority_snapshot_after=authority_snapshot,
        )
        return build_manifest(graph, self.private_key, proof_profile="authority_lifecycle")

    def _resign_mutated_manifest(self, manifest):
        payload = manifest["payload"]
        for node in payload["nodes"]:
            node["sha256"] = hashlib.sha256(
                canonical(node["data"])
            ).hexdigest()
        payload["root_digest"] = graph_root(payload)
        manifest["signature"] = base64.b64encode(
            self.private_key.sign(canonical(payload))
        ).decode()
        return manifest

    def _append_attestor_governance_action(
        self,
        manifest,
        *,
        operation,
        issued_at,
        action_id,
        public_key_b64=None,
        attestor_type=None,
        attestor_expires_at=None,
    ):
        policy = GovernancePolicy(
            policy_id=f"reference-{action_id}",
            version=1,
            threshold=1,
            members=(
                GovernanceMember.from_public_key(
                    self.governance_key.public_key(), "governor"
                ),
            ),
            allowed_actions=(operation,),
        )
        action = AttestorAuthorityService.build_action(
            action=operation,
            attestor_id="external-reference",
            reason=f"test {operation.lower()} governance replay",
            governance_policy_sha256=policy.digest,
            public_key_b64=public_key_b64,
            attestor_type=attestor_type,
            expires_at=attestor_expires_at,
            action_id=action_id,
            nonce=f"{action_id}-nonce",
            issued_at=issued_at,
        )
        approval_payload = {
            "governance_version": 1,
            "action_digest": hashlib.sha256(canonical(action)).hexdigest(),
            "governor_id": governor_id(self.governance_key.public_key()),
            "role": "governor",
            "approval_id": f"approval-{action_id}",
            "issued_at": issued_at + 10,
            "expires_at": issued_at + 200,
            "nonce": f"approval-{action_id}-nonce",
        }
        approval = {
            "payload": approval_payload,
            "signature": base64.b64encode(
                self.governance_key.sign(canonical(approval_payload))
            ).decode(),
            "algorithm": "Ed25519",
        }
        payload = manifest["payload"]
        payload["nodes"].extend([
            {
                "type": "governance_policy",
                "id": policy.digest,
                "sha256": "",
                "data": policy.as_dict(),
            },
            {
                "type": "governance_action",
                "id": action["action_id"],
                "sha256": "",
                "data": action,
            },
            {
                "type": "governance_approval",
                "id": approval_payload["approval_id"],
                "sha256": "",
                "data": approval,
            },
        ])
        payload["edges"].extend([
            {
                "from": "attestor_authority:external-reference",
                "relation": "DERIVED_FROM",
                "to": f"governance_action:{action['action_id']}",
            },
            {
                "from": f"governance_policy:{policy.digest}",
                "relation": "GOVERNS",
                "to": f"governance_action:{action['action_id']}",
            },
            {
                "from": f"governance_approval:{approval_payload['approval_id']}",
                "relation": "APPROVES",
                "to": f"governance_action:{action['action_id']}",
            },
        ])
        return action

    def test_adversarial_semantic_mutations_are_rejected(self):
        mutations = []

        def mutate(label, fn):
            mutations.append((label, fn))

        mutate("wrong intent", lambda p: p.__setitem__("intent_id", "forged-intent"))
        mutate("wrong authorization", lambda p: p.__setitem__("authorization_id", "forged-auth"))

        def wrong_receipt(p):
            node = next(n for n in p["nodes"] if n["type"] == "execution_receipt")
            node["data"]["payload"]["authorization_id"] = "forged-auth"
        mutate("wrong receipt", wrong_receipt)

        def wrong_claim(p):
            node = next(n for n in p["nodes"] if n["type"] == "outcome_claim")
            node["data"]["authorization_id"] = "forged-auth"
        mutate("wrong claim", wrong_claim)

        def wrong_attestor(p):
            node = next(n for n in p["nodes"] if n["type"] == "outcome_attestation")
            node["data"]["payload"]["attestor_id"] = "forged-attestor"
        mutate("wrong attestor", wrong_attestor)

        def wrong_governance_action(p):
            node = next(n for n in p["nodes"] if n["type"] == "governance_action")
            node["data"]["attestor_id"] = "forged-attestor"
        mutate("wrong governance action", wrong_governance_action)

        def wrong_governance_approval(p):
            node = next(n for n in p["nodes"] if n["type"] == "governance_approval")
            node["data"]["payload"]["action_digest"] = "00" * 32
        mutate("wrong governance approval", wrong_governance_approval)

        def blocked_decision(p):
            node = next(n for n in p["nodes"] if n["type"] == "decision")
            node["data"] = "BLOCK"
        mutate("BLOCK decision", blocked_decision)

        def wrong_capability(p):
            node = next(n for n in p["nodes"] if n["type"] == "execution_authorization")
            node["data"]["payload"]["capability_id"] = "forged-capability"
        mutate("wrong capability", wrong_capability)

        def wrong_identity(p):
            node = next(n for n in p["nodes"] if n["type"] == "execution_authorization")
            node["data"]["payload"]["identity_id"] = "forged-identity"
        mutate("wrong identity", wrong_identity)

        def mismatched_execution_action(p):
            node = next(n for n in p["nodes"] if n["type"] == "execution_authorization")
            node["data"]["payload"]["action"]["target"] = "forged-target"
        mutate("mismatched execution action payload", mismatched_execution_action)

        def mismatched_receipt_intent(p):
            node = next(n for n in p["nodes"] if n["type"] == "execution_receipt")
            node["data"]["payload"]["intent_id"] = "forged-intent"
        mutate("mismatched receipt intent", mismatched_receipt_intent)

        def wrong_authority_state(p):
            node = next(n for n in p["nodes"] if n["type"] == "authority_state")
            node["data"]["multiplier"] = 0.01
        mutate("wrong authority state", wrong_authority_state)

        def wrong_genesis_authority(p):
            node = next(n for n in p["nodes"] if n["type"] == "genesis_authority")
            node["data"]["authority_digest"] = "00" * 32
        mutate("wrong Genesis authority", wrong_genesis_authority)

        def wrong_authority_event(p):
            node = next(n for n in p["nodes"] if n["type"] == "authority_event")
            node["data"]["evidence_ref"] = "forged-claim"
        mutate("wrong authority event", wrong_authority_event)

        def wrong_authority_event_type(p):
            node = next(n for n in p["nodes"] if n["type"] == "authority_event")
            node["data"]["event_type"] = "EXECUTION_FAILED"
        mutate("wrong authority event type", wrong_authority_event_type)

        def wrong_authority_event_claim_digest(p):
            node = next(n for n in p["nodes"] if n["type"] == "authority_event")
            node["data"]["metadata"]["outcome_claim_sha256"] = "00" * 32
        mutate("wrong authority event claim digest", wrong_authority_event_claim_digest)

        def forged_post_learning_counters(p):
            node = next(n for n in p["nodes"] if n["type"] == "authority_state_after")
            node["data"]["successes"] = 999
        mutate("forged post-learning counters", forged_post_learning_counters)

        def wrong_authority_state_after(p):
            node = next(n for n in p["nodes"] if n["type"] == "authority_state_after")
            node["data"]["source_event_id"] = "forged-event"
        mutate("wrong post-learning authority state", wrong_authority_state_after)

        def disconnected_edge(p):
            edge = next(
                e for e in p["edges"]
                if e["relation"] == "AUTHORIZES"
            )
            edge["to"] = "action_intent:forged-intent"
        mutate("disconnected canonical edge", disconnected_edge)

        def mismatched_claim_receipt_digest(p):
            node = next(n for n in p["nodes"] if n["type"] == "outcome_claim")
            node["data"]["execution_receipt_sha256"] = "00" * 32
        mutate("mismatched claim receipt digest", mismatched_claim_receipt_digest)

        def swapped_attestation(p):
            node = next(n for n in p["nodes"] if n["type"] == "outcome_attestation")
            node["data"]["payload"]["claim"]["claim_id"] = "forged-claim"
        mutate("swapped attestation", swapped_attestation)

        valid_manifest = self._valid_manifest()
        for label, mutation in mutations:
            with self.subTest(label=label):
                manifest = json.loads(json.dumps(valid_manifest))
                mutation(manifest["payload"])
                self._resign_mutated_manifest(manifest)
                result = verify_proof(
                    manifest,
                    trusted_public_key_b64=manifest["issuer_public_key_b64"],
                )
                self.assertFalse(result["valid"], label)

    def test_authority_lifecycle_requires_independent_artifact_verification(self):
        valid_manifest = self._valid_manifest()
        for variant in ("missing", "false"):
            with self.subTest(variant=variant):
                manifest = json.loads(json.dumps(valid_manifest))
                if variant == "missing":
                    manifest["payload"].pop("verification", None)
                else:
                    manifest["payload"]["verification"]["all_signed_artifacts_valid"] = False
                self._resign_mutated_manifest(manifest)
                result = verify_manifest(manifest, manifest["issuer_public_key_b64"])
                self.assertFalse(result["valid"])
                self.assertIn("all signed artifacts", result["reason"])


    def _run_standalone_verifier(self, manifest, *arguments):
        proof_path = Path(self.tmp.name) / "governance-policy-pin-proof.json"
        proof_path.write_bytes(
            serialize_proof_package(build_proof_package(manifest))
        )
        verifier = Path(__file__).resolve().parents[1] / "tools" / "verigate_proof_verifier.py"
        return subprocess.run(
            [
                sys.executable,
                str(verifier),
                str(proof_path),
                *arguments,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_standalone_verifier_accepts_matching_trusted_governance_policy_digest(self):
        manifest = self._valid_manifest()
        policy_digest = next(
            node["data"]["governance_policy_sha256"]
            for node in manifest["payload"]["nodes"]
            if node["type"] == "governance_action"
        )

        result = self._run_standalone_verifier(
            manifest,
            "--public-key",
            str(self.public_path),
            "--trusted-governance-policy-sha256",
            policy_digest.upper(),
            "--trusted-governance-policy-sha256",
            "0" * 64,
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        trust = report["checks"]["governance_policy_trust_anchor"]
        self.assertTrue(trust["valid"], report)
        self.assertTrue(trust["pinned"], report)
        self.assertEqual(trust["policy_sha256"], [policy_digest])
        self.assertEqual(
            trust["trusted_policy_sha256"],
            sorted([policy_digest, "0" * 64]),
        )

    def test_standalone_verifier_rejects_malformed_governance_policy_digest(self):
        manifest = self._valid_manifest()

        result = self._run_standalone_verifier(
            manifest,
            "--public-key",
            str(self.public_path),
            "--trusted-governance-policy-sha256",
            "not-a-sha256-digest",
        )

        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("64 hexadecimal characters", result.stderr)

    def test_standalone_verifier_prints_unpinned_governance_policy_status(self):
        manifest = self._valid_manifest()

        result = self._run_standalone_verifier(
            manifest,
            "--public-key",
            str(self.public_path),
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("GOVERNANCE_POLICY_TRUST_ANCHOR NOT PINNED", result.stdout)
        self.assertIn("RESULT: VALID", result.stdout)

    def test_standalone_verifier_rejects_untrusted_governance_policy_digest(self):
        manifest = self._valid_manifest()

        result = self._run_standalone_verifier(
            manifest,
            "--public-key",
            str(self.public_path),
            "--trusted-governance-policy-sha256",
            "0" * 64,
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        trust = report["checks"]["governance_policy_trust_anchor"]
        self.assertFalse(trust["valid"], report)
        self.assertIn("governance policy", report["reason"].lower())

    def test_standalone_verifier_discloses_unpinned_governance_policy(self):
        manifest = self._valid_manifest()

        result = self._run_standalone_verifier(
            manifest,
            "--public-key",
            str(self.public_path),
            "--format",
            "json",
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        trust = report["checks"]["governance_policy_trust_anchor"]
        self.assertTrue(trust["valid"], report)
        self.assertFalse(trust["pinned"], report)

    def test_evidence_graph_rejects_reused_governance_policy_digest_with_different_content(self):
        policy_a = GovernancePolicy(
            policy_id="shared-policy-a",
            version=1,
            threshold=1,
            members=(
                GovernanceMember.from_public_key(
                    self.governance_key.public_key(), "governor"
                ),
            ),
            allowed_actions=("ATTESTOR_REGISTER",),
        )
        policy_b = GovernancePolicy(
            policy_id="shared-policy-b",
            version=1,
            threshold=1,
            members=(
                GovernanceMember.from_public_key(
                    self.governance_key.public_key(), "governor"
                ),
            ),
            allowed_actions=("ATTESTOR_ROTATE",),
        )
        attestor_key = Ed25519PrivateKey.generate()
        attestor_public_key = base64.b64encode(
            attestor_key.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        ).decode()
        service = AttestorAuthorityService(self.storage)
        graph = EvidenceGraph(self.storage, self.public_key)
        nodes = []
        edges = []
        verification = {}

        action_a = service.build_action(
            action="ATTESTOR_REGISTER",
            attestor_id="shared-policy-attestor",
            reason="initial registration",
            governance_policy_sha256=policy_a.digest,
            public_key_b64=attestor_public_key,
            attestor_type="EXTERNAL_VERIFIER",
            action_id="shared-policy-register",
            nonce="shared-policy-register-nonce",
        )
        action_b = service.build_action(
            action="ATTESTOR_ROTATE",
            attestor_id="shared-policy-attestor",
            reason="rotate under different policy",
            governance_policy_sha256=policy_b.digest,
            public_key_b64=attestor_public_key,
            attestor_type="EXTERNAL_VERIFIER",
            action_id="shared-policy-rotate",
            nonce="shared-policy-rotate-nonce",
        )

        for action, policy, envelope_digest in (
            (action_a, policy_a, policy_a.digest),
            (action_b, policy_b, policy_a.digest),
        ):
            graph._add_governance_envelope(
                {
                    "action": action,
                    "approvals": [_governance_approval(action, self.governance_key)],
                    "governance_policy": policy.as_dict(),
                    "governance_policy_sha256": envelope_digest,
                },
                subject_type="attestor_authority",
                subject_id="shared-policy-attestor",
                relation="GOVERNS",
                verification=verification,
                nodes=nodes,
                edges=edges,
            )

        self.assertFalse(
            verification["governance:shared-policy-rotate"]["valid"],
            verification,
        )
        self.assertIn(
            "reused for different policy content",
            verification["governance:shared-policy-rotate"]["reason"],
        )

    def test_authority_lifecycle_rejects_registry_snapshot_inconsistent_with_later_revocation(self):
        manifest = self._valid_manifest()
        attested_at = next(
            node["data"]["payload"]["attested_at"]
            for node in manifest["payload"]["nodes"]
            if node["type"] == "outcome_attestation"
        )
        self._append_attestor_governance_action(
            manifest,
            operation="ATTESTOR_REVOKE",
            issued_at=attested_at + 600,
            action_id="revoke-after-attestation-snapshot-mismatch",
        )
        # The history says REVOKED, but deliberately leave the signed registry
        # snapshot ACTIVE. Historical attestation time alone must not hide this
        # contradiction in the current registry snapshot.
        attestor = next(
            node for node in manifest["payload"]["nodes"]
            if node["type"] == "attestor_authority"
        )
        attestor["data"]["status"] = "ACTIVE"
        attestor["data"]["revoked_at"] = None
        self._resign_mutated_manifest(manifest)

        core_result = verify_proof(
            manifest,
            trusted_public_key_b64=manifest["issuer_public_key_b64"],
        )
        standalone_result = self._run_standalone_verifier(
            manifest,
            "--public-key",
            str(self.public_path),
        )
        self.assertFalse(
            core_result["valid"],
            "core verifier accepted a registry snapshot that contradicts the final governance state",
        )
        self.assertNotEqual(
            standalone_result.returncode,
            0,
            standalone_result.stdout + standalone_result.stderr,
        )

    def test_authority_lifecycle_accepts_attestation_after_governance_reactivation(self):
        manifest = self._valid_manifest()
        payload = manifest["payload"]
        attestation = next(
            node for node in payload["nodes"]
            if node["type"] == "outcome_attestation"
        )
        register_action = next(
            node["data"] for node in payload["nodes"]
            if node["type"] == "governance_action"
            and node["data"]["action"] == "ATTESTOR_REGISTER"
        )
        register_issued_at = register_action["issued_at"]
        revoke_at = register_issued_at + 100
        activate_at = register_issued_at + 300
        attested_at = register_issued_at + 400
        attestation["data"]["payload"]["attested_at"] = attested_at
        attestation["data"]["signature"] = base64.b64encode(
            self._last_attestor_private_key.sign(
                canonical(attestation["data"]["payload"])
            )
        ).decode()

        self._append_attestor_governance_action(
            manifest,
            operation="ATTESTOR_REVOKE",
            issued_at=revoke_at,
            action_id="revoke-before-reactivation",
        )
        self._append_attestor_governance_action(
            manifest,
            operation="ATTESTOR_ACTIVATE",
            issued_at=activate_at,
            action_id="activate-after-revocation",
        )
        attestor = next(
            node for node in payload["nodes"]
            if node["type"] == "attestor_authority"
        )
        attestor["data"]["status"] = "ACTIVE"
        # Storage retains revoked_at as an audit marker after reactivation.
        attestor["data"]["revoked_at"] = revoke_at + 20
        self._resign_mutated_manifest(manifest)

        core_result = verify_proof(
            manifest,
            trusted_public_key_b64=manifest["issuer_public_key_b64"],
        )
        standalone_result = self._run_standalone_verifier(
            manifest,
            "--public-key",
            str(self.public_path),
        )
        self.assertTrue(core_result["valid"], core_result)
        self.assertEqual(
            standalone_result.returncode,
            0,
            standalone_result.stdout + standalone_result.stderr,
        )

    def test_authority_lifecycle_rejects_forged_governance_approval_signature(self):
        manifest = self._valid_manifest()
        forged = json.loads(json.dumps(manifest))
        approval = next(
            node for node in forged["payload"]["nodes"]
            if node["type"] == "governance_approval"
        )
        approval["data"]["signature"] = base64.b64encode(b"forged-signature").decode()
        self._resign_mutated_manifest(forged)

        result = verify_proof(
            forged,
            trusted_public_key_b64=forged["issuer_public_key_b64"],
        )

        self.assertFalse(result["valid"], result)
        self.assertIn("governance", result["reason"].lower())


    def test_standalone_authority_proof_rejects_forged_governance_approval_signature(self):
        manifest = self._valid_manifest()
        forged = json.loads(json.dumps(manifest))
        approval = next(
            node for node in forged["payload"]["nodes"]
            if node["type"] == "governance_approval"
        )
        approval["data"]["signature"] = base64.b64encode(b"forged-signature").decode()
        self._resign_mutated_manifest(forged)

        proof_path = Path(self.tmp.name) / "forged-governance-proof.json"
        proof_path.write_bytes(
            serialize_proof_package(build_proof_package(forged))
        )
        verifier = Path(__file__).resolve().parents[1] / "tools" / "verigate_proof_verifier.py"
        result = subprocess.run(
            [
                sys.executable,
                str(verifier),
                str(proof_path),
                "--public-key",
                str(self.public_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("governance", result.stdout.lower())

    def test_standalone_verifier_accepts_historical_expired_governance_approval(self):
        root = Path(__file__).resolve().parents[1]
        proof = root / "examples" / "authority-proof" / "authority-proof.json"
        public_key = root / "examples" / "authority-proof" / "issuer.pub"
        verifier = root / "tools" / "verigate_proof_verifier.py"
        result = subprocess.run(
            [
                sys.executable,
                str(verifier),
                str(proof),
                "--public-key",
                str(public_key),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RESULT: VALID", result.stdout)


    def test_authority_lifecycle_rejects_forged_outcome_attestor_signature(self):
        manifest = self._valid_manifest()
        forged = json.loads(json.dumps(manifest))
        attestation = next(
            node for node in forged["payload"]["nodes"]
            if node["type"] == "outcome_attestation"
        )
        attestation["data"]["signature"] = base64.b64encode(b"forged-attestor-signature").decode()
        self._resign_mutated_manifest(forged)

        result = verify_proof(
            forged,
            trusted_public_key_b64=forged["issuer_public_key_b64"],
        )

        self.assertFalse(result["valid"], result)
        self.assertIn("attestation", result["reason"].lower())


    def test_standalone_verifier_rejects_forged_outcome_attestor_signature(self):
        manifest = self._valid_manifest()
        forged = json.loads(json.dumps(manifest))
        attestation = next(
            node for node in forged["payload"]["nodes"]
            if node["type"] == "outcome_attestation"
        )
        attestation["data"]["signature"] = base64.b64encode(b"forged-attestor-signature").decode()
        self._resign_mutated_manifest(forged)

        proof_path = Path(self.tmp.name) / "forged-outcome-attestation-proof.json"
        proof_path.write_bytes(
            serialize_proof_package(build_proof_package(forged))
        )
        verifier = Path(__file__).resolve().parents[1] / "tools" / "verigate_proof_verifier.py"
        result = subprocess.run(
            [
                sys.executable,
                str(verifier),
                str(proof_path),
                "--public-key",
                str(self.public_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("attestation", result.stdout.lower())


    def test_authority_lifecycle_rejects_unapproved_attestor_key_substitution(self):
        manifest = self._valid_manifest()
        forged = json.loads(json.dumps(manifest))
        attestor = next(
            node for node in forged["payload"]["nodes"]
            if node["type"] == "attestor_authority"
        )
        attestation = next(
            node for node in forged["payload"]["nodes"]
            if node["type"] == "outcome_attestation"
        )
        rogue_key = Ed25519PrivateKey.generate()
        rogue_raw = rogue_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        attestor["data"]["public_key_b64"] = base64.b64encode(rogue_raw).decode()
        attestor["data"]["key_id"] = hashlib.sha256(rogue_raw).hexdigest()
        attestation["data"]["signature"] = base64.b64encode(
            rogue_key.sign(canonical(attestation["data"]["payload"]))
        ).decode()
        self._resign_mutated_manifest(forged)

        result = verify_proof(
            forged,
            trusted_public_key_b64=forged["issuer_public_key_b64"],
        )

        self.assertFalse(result["valid"], result)
        self.assertIn("attestor", result["reason"].lower())

        proof_path = Path(self.tmp.name) / "unapproved-attestor-key-proof.json"
        proof_path.write_bytes(
            serialize_proof_package(build_proof_package(forged))
        )
        verifier = Path(__file__).resolve().parents[1] / "tools" / "verigate_proof_verifier.py"
        standalone = subprocess.run(
            [
                sys.executable,
                str(verifier),
                str(proof_path),
                "--public-key",
                str(self.public_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(standalone.returncode, 0, standalone.stdout)
        self.assertIn("attestor", standalone.stdout.lower())


    def test_authority_lifecycle_rejects_overflowing_governance_policy_without_exception(self):
        manifest = self._valid_manifest()
        forged = json.loads(json.dumps(manifest))
        policy_node = next(
            node for node in forged["payload"]["nodes"]
            if node["type"] == "governance_policy"
        )
        policy_node["data"]["version"] = float("inf")
        self._resign_mutated_manifest(forged)

        result = verify_manifest(
            forged,
            forged["issuer_public_key_b64"],
        )
        self.assertFalse(result["valid"], result)
        self.assertIn("governance", result["reason"].lower())

        proof_path = Path(self.tmp.name) / "overflowing-governance-policy-proof.json"
        proof_path.write_bytes(
            serialize_proof_package(build_proof_package(forged))
        )
        verifier = Path(__file__).resolve().parents[1] / "tools" / "verigate_proof_verifier.py"
        standalone = subprocess.run(
            [
                sys.executable,
                str(verifier),
                str(proof_path),
                "--public-key",
                str(self.public_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(standalone.returncode, 0, standalone.stdout)
        self.assertIn("governance", standalone.stdout.lower())

    def test_authority_lifecycle_rejects_oversized_timestamps_without_overflow(self):
        timestamp_mutations = (
            ("governance action issued_at", "governance_action", ("issued_at",)),
            ("governance action expires_at", "governance_action", ("expires_at",)),
            ("governance approval issued_at", "governance_approval", ("payload", "issued_at")),
            ("governance approval expires_at", "governance_approval", ("payload", "expires_at")),
            ("outcome attestation attested_at", "outcome_attestation", ("payload", "attested_at")),
        )
        valid_manifest = self._valid_manifest()

        for label, node_type, path in timestamp_mutations:
            for oversized in (10**400, -(10**400)):
                with self.subTest(field=label, value_sign="negative" if oversized < 0 else "positive"):
                    manifest = json.loads(json.dumps(valid_manifest))
                    node = next(
                        item for item in manifest["payload"]["nodes"]
                        if item["type"] == node_type
                    )
                    target = node["data"]
                    for key in path[:-1]:
                        target = target[key]
                    target[path[-1]] = oversized
                    self._resign_mutated_manifest(manifest)

                    result = verify_proof(
                        manifest,
                        trusted_public_key_b64=manifest["issuer_public_key_b64"],
                    )
                    self.assertFalse(result["valid"], result)

                    proof_path = Path(self.tmp.name) / "oversized-timestamp-proof.json"
                    proof_path.write_bytes(
                        serialize_proof_package(build_proof_package(manifest))
                    )
                    verifier = Path(__file__).resolve().parents[1] / "tools" / "verigate_proof_verifier.py"
                    standalone = subprocess.run(
                        [
                            sys.executable,
                            str(verifier),
                            str(proof_path),
                            "--public-key",
                            str(self.public_path),
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertNotEqual(standalone.returncode, 0, standalone.stdout)
                    self.assertNotIn("Traceback", standalone.stderr)


    def test_authority_lifecycle_rejects_out_of_order_attestor_governance_history(self):
        original_manifest = self._valid_manifest()
        self._apply_attestor_lifecycle_action(
            "ATTESTOR_ROTATE",
            new_key=Ed25519PrivateKey.generate(),
        )
        authority_snapshot_after = next(
            node["data"] for node in original_manifest["payload"]["nodes"]
            if node["type"] == "authority_state_after"
        )
        graph = EvidenceGraph(self.storage, self.public_key).build(
            original_manifest["payload"]["authorization_id"],
            authority_snapshot_after=authority_snapshot_after,
        )
        manifest = build_manifest(
            graph,
            self.private_key,
            proof_profile="authority_lifecycle",
        )
        forged = json.loads(json.dumps(manifest))
        nodes = forged["payload"]["nodes"]
        action_indices = [
            index for index, node in enumerate(nodes)
            if node["type"] == "governance_action"
            and node["data"].get("attestor_id") == "external-reference"
        ]
        self.assertEqual(len(action_indices), 2)
        first, second = action_indices
        nodes[first], nodes[second] = nodes[second], nodes[first]
        self._resign_mutated_manifest(forged)

        result = verify_proof(
            forged,
            trusted_public_key_b64=forged["issuer_public_key_b64"],
        )
        self.assertFalse(result["valid"], result)
        self.assertIn("chronological", result["reason"].lower())

        proof_path = Path(self.tmp.name) / "out-of-order-attestor-history.json"
        proof_path.write_bytes(
            serialize_proof_package(build_proof_package(forged))
        )
        verifier = Path(__file__).resolve().parents[1] / "tools" / "verigate_proof_verifier.py"
        standalone = subprocess.run(
            [
                sys.executable,
                str(verifier),
                str(proof_path),
                "--public-key",
                str(self.public_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(standalone.returncode, 0, standalone.stdout)
        self.assertIn("chronological", standalone.stdout.lower())

    def test_authority_lifecycle_rejects_governance_action_effective_before_quorum(self):
        manifest = self._valid_manifest()
        forged = json.loads(json.dumps(manifest))
        action_node = next(
            node for node in forged["payload"]["nodes"]
            if node["type"] == "governance_action"
        )
        action_ref = f"governance_action:{action_node['id']}"
        approval_nodes = [
            next(
                node for node in forged["payload"]["nodes"]
                if f"{node['type']}:{node['id']}" == edge["from"]
            )
            for edge in forged["payload"]["edges"]
            if edge.get("relation") == "APPROVES" and edge.get("to") == action_ref
        ]
        quorum_time = max(
            [
                float(action_node["data"]["issued_at"]),
                *[
                    float(node["data"]["payload"]["issued_at"])
                    for node in approval_nodes
                ],
            ]
        )
        action_node["data"]["effective_at"] = quorum_time - 1.0
        self._resign_mutated_manifest(forged)

        result = verify_proof(
            forged,
            trusted_public_key_b64=forged["issuer_public_key_b64"],
        )
        self.assertFalse(result["valid"], result)
        self.assertIn("application timestamp", result["reason"].lower())

        proof_path = Path(self.tmp.name) / "pre-quorum-effective-at-proof.json"
        proof_path.write_bytes(
            serialize_proof_package(build_proof_package(forged))
        )
        verifier = Path(__file__).resolve().parents[1] / "tools" / "verigate_proof_verifier.py"
        standalone = subprocess.run(
            [
                sys.executable,
                str(verifier),
                str(proof_path),
                "--public-key",
                str(self.public_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(standalone.returncode, 0, standalone.stdout)
        self.assertIn("application timestamp", standalone.stdout.lower())

    def _assert_standalone_proof_valid(self, manifest, filename):
        proof_path = Path(self.tmp.name) / filename
        proof_path.write_bytes(
            serialize_proof_package(build_proof_package(manifest))
        )
        verifier = Path(__file__).resolve().parents[1] / "tools" / "verigate_proof_verifier.py"
        result = subprocess.run(
            [
                sys.executable,
                str(verifier),
                str(proof_path),
                "--public-key",
                str(self.public_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def _apply_attestor_lifecycle_action(self, action_name, *, new_key=None):
        service = AttestorAuthorityService(self.storage)
        action = service.build_action(
            action=action_name,
            attestor_id="external-reference",
            reason="historical attestation regression",
            governance_policy_sha256=self.governance_policy.digest,
            public_key_b64=(
                base64.b64encode(
                    new_key.public_key().public_bytes(
                        serialization.Encoding.Raw,
                        serialization.PublicFormat.Raw,
                    )
                ).decode()
                if new_key is not None else None
            ),
            attestor_type="EXTERNAL_VERIFIER" if new_key is not None else None,
        )
        service.apply(
            action,
            [_governance_approval(action, self.governance_key)],
            self.governance_policy,
        )

    def test_attestor_rotation_does_not_reactivate_revoked_authority(self):
        original_manifest = self._valid_manifest()
        service = AttestorAuthorityService(self.storage)

        revoke = service.build_action(
            action="ATTESTOR_REVOKE",
            attestor_id="external-reference",
            reason="revoke before key replacement",
            governance_policy_sha256=self.governance_policy.digest,
        )
        service.apply(
            revoke,
            [_governance_approval(revoke, self.governance_key)],
            self.governance_policy,
        )

        rotated_key = Ed25519PrivateKey.generate()
        raw_key = rotated_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        rotate = service.build_action(
            action="ATTESTOR_ROTATE",
            attestor_id="external-reference",
            reason="replace key without restoring authority",
            governance_policy_sha256=self.governance_policy.digest,
            public_key_b64=base64.b64encode(raw_key).decode(),
            attestor_type="EXTERNAL_VERIFIER",
        )
        service.apply(
            rotate,
            [_governance_approval(rotate, self.governance_key)],
            self.governance_policy,
        )

        authority_snapshot_after = next(
            node["data"] for node in original_manifest["payload"]["nodes"]
            if node["type"] == "authority_state_after"
        )
        graph = EvidenceGraph(self.storage, self.public_key).build(
            original_manifest["payload"]["authorization_id"],
            authority_snapshot_after=authority_snapshot_after,
        )
        self.assertTrue(
            graph["verification"]["all_signed_artifacts_valid"],
            graph["verification"],
        )
        forged = build_manifest(
            graph,
            self.private_key,
            proof_profile="authority_lifecycle",
        )
        attestation_node = next(
            node for node in forged["payload"]["nodes"]
            if node["type"] == "outcome_attestation"
        )
        attestation_payload = attestation_node["data"]["payload"]
        attestation_payload["attested_at"] = time.time()
        attestation_node["data"]["signature"] = base64.b64encode(
            rotated_key.sign(canonical(attestation_payload))
        ).decode()
        self._resign_mutated_manifest(forged)

        core_result = verify_manifest(forged, forged["issuer_public_key_b64"])
        self.assertFalse(core_result["valid"], core_result)
        self.assertIn("not active", core_result["reason"].lower())

        proof_path = Path(self.tmp.name) / "revoked-attestor-rotation-proof.json"
        proof_path.write_bytes(
            serialize_proof_package(build_proof_package(forged))
        )
        verifier = Path(__file__).resolve().parents[1] / "tools" / "verigate_proof_verifier.py"
        standalone = subprocess.run(
            [
                sys.executable,
                str(verifier),
                str(proof_path),
                "--public-key",
                str(self.public_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(standalone.returncode, 0, standalone.stdout)
        self.assertIn("not active", standalone.stdout.lower())

        receipt_data = next(
            node["data"] for node in original_manifest["payload"]["nodes"]
            if node["type"] == "execution_receipt"
        )
        observed_data = next(
            node["data"] for node in original_manifest["payload"]["nodes"]
            if node["type"] == "observed_effect"
        )
        claim = build_outcome_claim(
            receipt_data,
            status="SUCCEEDED",
            executor_id="executor-reference",
            evidence_kind=observed_data["evidence_kind"],
            evidence_ref=observed_data["evidence_ref"],
            result_sha256=observed_data["result_sha256"],
            observed_effect=observed_data,
        )
        attestation = build_outcome_attestation(
            claim,
            attestor_id="external-reference",
            attestor_type="EXTERNAL_VERIFIER",
            private_key=rotated_key,
        )
        with self.assertRaisesRegex(PermissionError, "active"):
            OutcomeAttestationService(self.storage, self.public_key).verify_and_record(
                attestation
            )

    def test_historical_attestation_survives_attestor_key_rotation(self):
        original_manifest = self._valid_manifest()
        self._apply_attestor_lifecycle_action(
            "ATTESTOR_ROTATE",
            new_key=Ed25519PrivateKey.generate(),
        )

        authority_snapshot_after = next(
            node["data"] for node in original_manifest["payload"]["nodes"]
            if node["type"] == "authority_state_after"
        )
        graph = EvidenceGraph(self.storage, self.public_key).build(
            original_manifest["payload"]["authorization_id"],
            authority_snapshot_after=authority_snapshot_after,
        )
        self.assertTrue(
            graph["verification"]["all_signed_artifacts_valid"],
            graph["verification"],
        )
        rebuilt = build_manifest(
            graph,
            self.private_key,
            proof_profile="authority_lifecycle",
        )
        result = verify_manifest(
            rebuilt,
            rebuilt["issuer_public_key_b64"],
        )

        self.assertTrue(result["valid"], result)
        self._assert_standalone_proof_valid(
            rebuilt,
            "historical-attestation-after-rotation.json",
        )

    def test_historical_attestation_survives_later_attestor_revocation(self):
        original_manifest = self._valid_manifest()
        self._apply_attestor_lifecycle_action("ATTESTOR_REVOKE")

        authority_snapshot_after = next(
            node["data"] for node in original_manifest["payload"]["nodes"]
            if node["type"] == "authority_state_after"
        )
        graph = EvidenceGraph(self.storage, self.public_key).build(
            original_manifest["payload"]["authorization_id"],
            authority_snapshot_after=authority_snapshot_after,
        )
        self.assertTrue(
            graph["verification"]["all_signed_artifacts_valid"],
            graph["verification"],
        )
        rebuilt = build_manifest(
            graph,
            self.private_key,
            proof_profile="authority_lifecycle",
        )
        result = verify_manifest(
            rebuilt,
            rebuilt["issuer_public_key_b64"],
        )

        self.assertTrue(result["valid"], result)
        self._assert_standalone_proof_valid(
            rebuilt,
            "historical-attestation-after-revocation.json",
        )


if __name__ == "__main__":
    unittest.main()
