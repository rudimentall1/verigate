import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.proof_adversarial import ProofMutation, assert_all_rejected, run
from core.evidence_manifest import build_manifest, verify_manifest
from tests.test_proof_profiles import _mcp_graph


class ProofAdversarialEngineTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.manifest = build_manifest(_mcp_graph(), self.key, proof_profile="mcp_execution")

    def test_profile_aware_mutations_are_all_rejected(self):
        results = run(self.manifest, self.key)
        self.assertEqual({r.mutation_id for r in results}, {
            "MCP-TARGET-DRIFT",
            "MCP-AUTH-ACTION-SWAP",
            "MCP-CLAIM-RECEIPT-SWAP",
            "MCP-SELF-REPORT",
        })
        assert_all_rejected(results)

    def test_engine_resigns_mutations_before_verification(self):
        observed = []

        def verifier(candidate):
            self.assertNotEqual(candidate["signature"], self.manifest["signature"])
            result = verify_manifest(candidate)
            observed.append(result)
            return result

        results = run(self.manifest, self.key, mutations=(
            ProofMutation("MCP-TARGET-DRIFT", "change target", lambda m: m["payload"]["nodes"][0]["data"].update(target="tampered.tool")),
        ), verifier=verifier)
        self.assertEqual(len(observed), 1)
        self.assertTrue(results[0].rejected)

    def test_custom_mutation_suite_is_supported(self):
        results = run(self.manifest, self.key, mutations=(
            ProofMutation("CUSTOM", "disconnect canonical edge", lambda m: m["payload"]["edges"].__setitem__(0, {
                **m["payload"]["edges"][0], "to": "decision:other"
            })),
        ))
        assert_all_rejected(results)


if __name__ == "__main__":
    unittest.main()
