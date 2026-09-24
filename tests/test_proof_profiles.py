import unittest
import base64
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from core.evidence_manifest import build_manifest, verify_manifest, canonical, graph_root

from core.proof_profiles import PROOF_PROFILES, assurance_claims, profile_spec


class ProofProfileRegistryTests(unittest.TestCase):
    def test_profiles_are_declarative_and_expose_assurance_claims(self):
        self.assertIn('integrity', PROOF_PROFILES)
        self.assertIn('authority_lifecycle', PROOF_PROFILES)
        self.assertIn('mcp_execution', PROOF_PROFILES)
        self.assertEqual(assurance_claims('integrity'), ['signed_manifest', 'graph_integrity'])
        self.assertIn('independent_outcome_attestation', assurance_claims('authority_lifecycle'))
        self.assertIn('mcp_target_binding', assurance_claims('mcp_execution'))
        self.assertIs(profile_spec('authority_lifecycle'), PROOF_PROFILES['authority_lifecycle'])

    def test_mcp_profile_accepts_bound_execution_graph(self):
        key = Ed25519PrivateKey.generate()
        graph = {
            "authorization_id": "auth", "intent_id": "intent", "agent_id": "agent", "graph_version": 1,
            "nodes": [
                {"type": "action_intent", "id": "intent", "sha256": "", "data": {"intent_id": "intent", "action": {"action_type": "mcp.tool.call", "target": "orders.create"}}},
                {"type": "execution_authorization", "id": "auth", "sha256": "", "data": {"payload": {"authorization_id": "auth", "intent_id": "intent", "action_sha256": "a"}}},
                {"type": "execution_receipt", "id": "receipt", "sha256": "", "data": {"payload": {"authorization_id": "auth", "action_sha256": "a"}}},
                {"type": "outcome_claim", "id": "claim", "sha256": "", "data": {"authorization_id": "auth", "execution_receipt_sha256": "" , "evidence_kind": "MCP_RESULT"}},
                {"type": "outcome_attestation", "id": "att", "sha256": "", "data": {"attestor_id": "attestor"}},
                {"type": "attestor_authority", "id": "attestor", "sha256": "", "data": {"attestor_id": "attestor"}},
            ],
            "edges": [
                {"from": "action_intent:intent", "relation": "EVALUATED_AS", "to": "action_intent:intent"},
                {"from": "execution_authorization:auth", "relation": "PRODUCES", "to": "execution_receipt:receipt"},
                {"from": "execution_receipt:receipt", "relation": "OBSERVED_BY", "to": "outcome_claim:claim"},
                {"from": "outcome_attestation:att", "relation": "ATTESTS", "to": "outcome_claim:claim"},
                {"from": "attestor_authority:attestor", "relation": "AUTHORIZES", "to": "outcome_attestation:att"},
            ],
            "verification": {"all_signed_artifacts_valid": True}, "audit": {},
        }
        import hashlib, json
        for n in graph["nodes"]:
            n["sha256"] = hashlib.sha256(json.dumps(n["data"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        graph["nodes"][3]["data"]["execution_receipt_sha256"] = hashlib.sha256(json.dumps(graph["nodes"][2]["data"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        graph["nodes"][3]["sha256"] = hashlib.sha256(json.dumps(graph["nodes"][3]["data"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        manifest = build_manifest(graph, key, proof_profile="mcp_execution")
        result = verify_manifest(manifest, manifest["issuer_public_key_b64"])
        self.assertTrue(result["valid"])
        self.assertIn("mcp_target_binding", result["assurance"]["claims"])

    def test_unknown_profile_has_no_assurance_claims(self):
        self.assertEqual(assurance_claims('does_not_exist'), [])
        self.assertIsNone(profile_spec('does_not_exist'))


if __name__ == '__main__':
    unittest.main()
