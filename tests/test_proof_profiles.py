import base64
import copy
import hashlib
import json
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.evidence_manifest import build_manifest, verify_manifest, canonical, graph_root
from core.proof_validators.common import intent_context_digest
from core.proof_profiles import PROOF_PROFILES, assurance_claims, profile_spec


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _mcp_graph():
    action = {
        "intent_id": "intent",
        "agent_id": "agent",
        "action_type": "mcp.tool.call",
        "target": "orders.create",
        "resource": "",
        "amount": None,
        "asset": None,
        "network": None,
        "metadata": {},
        "purpose": "order execution",
        "declared_context": {"environment": "production", "order_id": "ORD-1"},
        "parent_intent_id": None,
        "requested_capability": "orders.execute",
        "constraints": {"max_items": 10},
        "timestamp": 1.0,
    }
    receipt = {
        "payload": {
            "receipt_id": "receipt",
            "authorization_id": "auth",
            "intent_id": "intent",
            "agent_id": "agent",
            "action_sha256": _digest(action),
        }
    }
    claim = {
        "outcome_claim_version": 1,
        "claim_id": "claim",
        "authorization_id": "auth",
        "execution_receipt_sha256": _digest(receipt),
        "action_sha256": _digest(action),
        "intent_id": "intent",
        "agent_id": "agent",
        "executor_id": "mcp-executor",
        "status": "SUCCEEDED",
        "evidence_kind": "MCP_RESULT",
        "evidence_ref": "mcp:orders.create:1",
        "result_sha256": "b" * 64,
    }
    attestation_payload = {
        "outcome_attestation_version": 1,
        "attestation_id": "att",
        "claim": claim,
        "claim_sha256": _digest(claim),
        "attestor_id": "attestor",
        "attestor_type": "EXTERNAL_VERIFIER",
    }
    nodes = [
        {"type": "action_intent", "id": "intent", "data": action},
        {"type": "decision", "id": "intent", "data": {"decision": "ALLOW", "intent_id": "intent", "context_sha256": intent_context_digest(action)}},
        {"type": "execution_authorization", "id": "auth", "data": {"payload": {
            "authorization_id": "auth", "intent_id": "intent", "agent_id": "agent",
            "action": action, "action_sha256": _digest(action),
        }}},
        {"type": "execution_receipt", "id": "receipt", "data": receipt},
        {"type": "outcome_claim", "id": "claim", "data": claim},
        {"type": "outcome_attestation", "id": "att", "data": {"payload": attestation_payload}},
        {"type": "attestor_authority", "id": "attestor", "data": {
            "attestor_id": "attestor", "attestor_type": "EXTERNAL_VERIFIER", "status": "ACTIVE",
        }},
    ]
    for node in nodes:
        node["sha256"] = _digest(node["data"])
    return {
        "authorization_id": "auth",
        "intent_id": "intent",
        "agent_id": "agent",
        "graph_version": 1,
        "nodes": nodes,
        "edges": [
            {"from": "action_intent:intent", "relation": "EVALUATED_AS", "to": "decision:intent"},
            {"from": "decision:intent", "relation": "MINTS", "to": "execution_authorization:auth"},
            {"from": "execution_authorization:auth", "relation": "PRODUCES", "to": "execution_receipt:receipt"},
            {"from": "execution_receipt:receipt", "relation": "OBSERVED_BY", "to": "outcome_claim:claim"},
            {"from": "outcome_attestation:att", "relation": "ATTESTS", "to": "outcome_claim:claim"},
            {"from": "attestor_authority:attestor", "relation": "AUTHORIZES", "to": "outcome_attestation:att"},
        ],
        "verification": {"all_signed_artifacts_valid": True},
        "audit": {},
    }


def _manifest():
    key = Ed25519PrivateKey.generate()
    return build_manifest(_mcp_graph(), key, proof_profile="mcp_execution"), key


def _resign(manifest, key):
    manifest = copy.deepcopy(manifest)
    payload = manifest["payload"]
    for node in payload["nodes"]:
        node["sha256"] = _digest(node["data"])
    payload["root_digest"] = graph_root(payload)
    manifest["signature"] = base64.b64encode(
        key.sign(canonical(payload))
    ).decode("ascii")
    return manifest


class ProofProfileRegistryTests(unittest.TestCase):
    def test_profiles_are_declarative_and_expose_assurance_claims(self):
        self.assertIn("integrity", PROOF_PROFILES)
        self.assertIn("authority_lifecycle", PROOF_PROFILES)
        self.assertIn("mcp_execution", PROOF_PROFILES)
        self.assertEqual(assurance_claims("integrity"), ["signed_manifest", "graph_integrity"])
        self.assertIn("independent_mcp_outcome", assurance_claims("mcp_execution"))
        self.assertIs(profile_spec("authority_lifecycle"), PROOF_PROFILES["authority_lifecycle"])

    def test_mcp_profile_accepts_bound_execution_graph(self):
        manifest, key = _manifest()
        result = verify_manifest(manifest, manifest["issuer_public_key_b64"])
        self.assertTrue(result["valid"])
        self.assertIn("mcp_target_binding", result["assurance"]["claims"])

    def test_mcp_profile_rejects_self_report_attestation(self):
        manifest, key = _manifest()
        manifest["payload"]["nodes"][5]["data"]["payload"]["attestor_type"] = "EXECUTOR_SELF_REPORT"
        manifest["payload"]["nodes"][6]["data"]["attestor_type"] = "EXECUTOR"
        manifest["payload"]["nodes"][5]["sha256"] = _digest(manifest["payload"]["nodes"][5]["data"])
        manifest["payload"]["nodes"][6]["sha256"] = _digest(manifest["payload"]["nodes"][6]["data"])
        manifest = _resign(manifest, key)
        self.assertFalse(verify_manifest(manifest)["valid"])

    def test_mcp_profile_rejects_action_target_drift_even_after_resigning(self):
        manifest, key = _manifest()
        manifest["payload"]["nodes"][0]["data"]["target"] = "orders.delete"
        manifest["payload"]["nodes"][0]["sha256"] = _digest(manifest["payload"]["nodes"][0]["data"])
        manifest = _resign(manifest, key)
        self.assertFalse(verify_manifest(manifest)["valid"])

    def test_mcp_profile_rejects_authorization_action_swap_even_after_resigning(self):
        manifest, key = _manifest()
        manifest["payload"]["nodes"][2]["data"]["payload"]["action"]["target"] = "orders.delete"
        manifest["payload"]["nodes"][2]["sha256"] = _digest(manifest["payload"]["nodes"][2]["data"])
        manifest = _resign(manifest, key)
        self.assertFalse(verify_manifest(manifest)["valid"])

    def test_mcp_profile_rejects_claim_receipt_swap_even_after_resigning(self):
        manifest, key = _manifest()
        manifest["payload"]["nodes"][4]["data"]["execution_receipt_sha256"] = "c" * 64
        manifest["payload"]["nodes"][4]["sha256"] = _digest(manifest["payload"]["nodes"][4]["data"])
        manifest = _resign(manifest, key)
        self.assertFalse(verify_manifest(manifest)["valid"])

    def test_mcp_profile_rejects_disconnected_evaluation_edge(self):
        manifest, key = _manifest()
        manifest["payload"]["edges"][0]["to"] = "decision:other"
        manifest = _resign(manifest, key)
        self.assertFalse(verify_manifest(manifest)["valid"])

    def test_unknown_profile_has_no_assurance_claims(self):
        self.assertEqual(assurance_claims("does_not_exist"), [])
        self.assertIsNone(profile_spec("does_not_exist"))


if __name__ == "__main__":
    unittest.main()
