import copy
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.evidence_manifest import build_manifest
from core.offline_verifier import verify_proof
from core.proof_engine import canonical
from core.evidence import EvidenceGraph
from core.proof_package import (
    PACKAGE_MEDIA_TYPE,
    PACKAGE_PROTOCOL,
    build_proof_package,
    parse_proof_package,
    serialize_proof_package,
    verify_proof_package,
)


def node(kind, ident, data):
    import hashlib
    return {
        "type": kind,
        "id": ident,
        "sha256": hashlib.sha256(canonical(data)).hexdigest(),
        "data": data,
    }


class ProofPackageTests(unittest.TestCase):
    def _manifest(self):
        key = Ed25519PrivateKey.generate()
        graph = {
            "authorization_id": "auth-1",
            "intent_id": "intent-1",
            "agent_id": "agent-1",
            "graph_version": 1,
            "nodes": [node("action_intent", "intent-1", {"intent_id": "intent-1"})],
            "edges": [],
            "verification": {},
            "audit": {},
        }
        return build_manifest(graph, key)

    def test_round_trip_is_deterministic_and_offline(self):
        manifest = self._manifest()
        package = build_proof_package(manifest)
        raw = serialize_proof_package(package)
        self.assertEqual(raw, serialize_proof_package(parse_proof_package(raw)))
        result = verify_proof_package(raw)
        self.assertTrue(result["valid"], result)
        self.assertTrue(result["package_valid"])
        self.assertEqual(package["package"]["media_type"], PACKAGE_MEDIA_TYPE)
        self.assertEqual(package["package"]["protocol"], PACKAGE_PROTOCOL)
        self.assertEqual(package["package"]["proof_profile"], "integrity")
        self.assertTrue(package["package"]["manifest_sha256"])
        self.assertEqual(package["package"]["node_count"], 1)
        self.assertEqual(package["package"]["edge_count"], 0)
        self.assertEqual(len(package["package"]["node_inventory"]), 1)
        self.assertEqual(package["package"]["graph_root_digest"], manifest["payload"]["root_digest"])
        self.assertTrue(verify_proof(manifest)["valid"])

    def test_package_digest_rejects_envelope_tampering(self):
        package = build_proof_package(self._manifest())
        tampered = copy.deepcopy(package)
        tampered["package"]["manifest"]["payload"]["agent_id"] = "forged-agent"
        result = verify_proof_package(tampered)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "proof package digest mismatch")

    def test_manifest_signature_rejects_tampering_after_repacking(self):
        package = build_proof_package(self._manifest())
        tampered = copy.deepcopy(package)
        tampered["package"]["manifest"]["payload"]["agent_id"] = "forged-agent"
        tampered["package"]["agent_id"] = "forged-agent"
        tampered["package"]["manifest_sha256"] = __import__("hashlib").sha256(
            canonical(tampered["package"]["manifest"])
        ).hexdigest()
        import hashlib
        tampered["package_sha256"] = hashlib.sha256(canonical(tampered["package"])).hexdigest()
        result = verify_proof_package(tampered)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "invalid manifest signature")

    def test_node_inventory_tampering_fails_closed(self):
        package = build_proof_package(self._manifest())
        tampered = copy.deepcopy(package)
        tampered["package"]["node_inventory"][0]["type"] = "forged"
        tampered["package_sha256"] = __import__("hashlib").sha256(
            canonical(tampered["package"])
        ).hexdigest()
        result = verify_proof_package(tampered)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "proof package node inventory mismatch")

    def test_manifest_metadata_tampering_fails_closed(self):
        package = build_proof_package(self._manifest())
        tampered = copy.deepcopy(package)
        tampered["package"]["proof_profile"] = "authority_lifecycle"
        tampered["package_sha256"] = __import__("hashlib").sha256(
            canonical(tampered["package"])
        ).hexdigest()
        result = verify_proof_package(tampered)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "proof package proof_profile mismatch")

    def test_manifest_replacement_with_recomputed_package_digest_fails_closed(self):
        package = build_proof_package(self._manifest())
        replacement = self._manifest()
        package["package"]["manifest"] = replacement
        package["package_sha256"] = __import__("hashlib").sha256(
            canonical(package["package"])
        ).hexdigest()
        result = verify_proof_package(package)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "proof package manifest digest mismatch")

    def test_unsupported_protocol_fails_closed(self):
        package = build_proof_package(self._manifest())
        package["package"]["protocol"] = "future-protocol"
        result = verify_proof_package(package)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "unsupported proof package protocol")

    def test_unsupported_version_fails_closed(self):
        package = build_proof_package(self._manifest())
        package["package"]["package_version"] = 999
        result = verify_proof_package(package)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "unsupported proof package version")

    def test_missing_manifest_fails_closed(self):
        package = build_proof_package(self._manifest())
        del package["package"]["manifest"]
        package["package_sha256"] = __import__("hashlib").sha256(
            canonical(package["package"])
        ).hexdigest()
        result = verify_proof_package(package)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "proof package manifest is missing")

    def test_invalid_bytes_are_rejected(self):
        result = verify_proof_package(b"not-json")
        self.assertFalse(result["valid"])
        self.assertFalse(result["package_valid"])


if __name__ == "__main__":
    unittest.main()
