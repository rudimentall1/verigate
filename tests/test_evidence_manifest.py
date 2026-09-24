import base64
import hashlib
import json
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from core.evidence_manifest import build_manifest, verify_manifest


class EvidenceManifestTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.graph = {
            "authorization_id": "auth-1",
            "intent_id": "intent-1",
            "agent_id": "agent-1",
            "graph_version": 1,
            "nodes": [
                {"type": "action_intent", "id": "intent-1", "sha256": "", "data": {"intent_id": "intent-1", "action": "mcp.tool.call"}},
                {"type": "decision", "id": "intent-1", "sha256": "", "data": {"decision": "ALLOW"}},
            ],
            "edges": [
                {"from": "action_intent:intent-1", "relation": "EVALUATED_AS", "to": "decision:intent-1"},
            ],
            "verification": {"decision_receipt": {"valid": True, "reason": "valid"}},
            "audit": {"intent_id": "intent-1", "recorded": True},
        }
        for node in self.graph["nodes"]:
            node["sha256"] = hashlib.sha256(json.dumps(node["data"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

    def test_manifest_is_deterministic_and_self_verifying(self):
        a = build_manifest(self.graph, self.key)
        b = build_manifest(self.graph, self.key)
        self.assertEqual(a, b)
        result = verify_manifest(a)
        self.assertTrue(result["valid"])
        self.assertEqual(result["node_count"], 2)
        self.assertEqual(result["edge_count"], 1)
        self.assertEqual(result["assurance"]["profile"], "integrity")
        self.assertEqual(result["assurance"]["claims"], ["signed_manifest", "graph_integrity"])

    def test_node_tamper_fails_before_signature_trust(self):
        manifest = build_manifest(self.graph, self.key)
        manifest["payload"]["nodes"][0]["data"]["action"] = "evil.action"
        result = verify_manifest(manifest)
        self.assertFalse(result["valid"])
        self.assertIn("node digest mismatch", result["reason"])

    def test_edge_tamper_fails_root_verification(self):
        manifest = build_manifest(self.graph, self.key)
        manifest["payload"]["edges"][0]["relation"] = "MINTS"
        result = verify_manifest(manifest)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "evidence Merkle root mismatch")

    def test_signature_tamper_fails(self):
        manifest = build_manifest(self.graph, self.key)
        manifest["signature"] = base64.b64encode(b"tampered").decode()
        result = verify_manifest(manifest)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "invalid manifest signature")

    def test_authority_lifecycle_profile_requires_complete_chain(self):
        with self.assertRaises(ValueError):
            build_manifest(self.graph, self.key, proof_profile="authority_lifecycle")

    def test_authority_lifecycle_profile_rejects_signed_stripped_graph(self):
        graph = json.loads(json.dumps(self.graph))
        graph["manifest_version"] = 1
        graph["proof_profile"] = "authority_lifecycle"
        manifest = {"payload": graph, "signature": "", "algorithm": "Ed25519", "issuer_public_key_b64": ""}
        result = verify_manifest(manifest)
        self.assertFalse(result["valid"])
        self.assertIn("proof profile missing required nodes", result["reason"])

    def test_invalid_evidence_cannot_be_presented_as_valid_proof(self):
        graph = json.loads(json.dumps(self.graph))
        graph["verification"]["execution_receipt"] = {"valid": False, "reason": "tampered receipt"}
        manifest = build_manifest(graph, self.key)
        result = verify_manifest(manifest)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "evidence verification failed")
        self.assertEqual(result["invalid_evidence"], ["execution_receipt"])

    def test_trusted_issuer_key_is_explicit(self):
        manifest = build_manifest(self.graph, self.key)
        raw = self.key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        trusted = base64.b64encode(raw).decode("ascii")
        self.assertTrue(verify_manifest(manifest, trusted)["embedded_issuer_trusted"])
        other = Ed25519PrivateKey.generate().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        other_b64 = base64.b64encode(other).decode("ascii")
        result = verify_manifest(manifest, other_b64)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "issuer public key is not trusted")

    def test_dangling_edge_is_rejected(self):
        graph = json.loads(json.dumps(self.graph))
        graph["edges"].append({"from": "decision:intent-1", "relation": "PROVES", "to": "missing:node"})
        manifest = build_manifest(graph, self.key)
        result = verify_manifest(manifest)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "manifest contains dangling edge")


if __name__ == "__main__":
    unittest.main()
