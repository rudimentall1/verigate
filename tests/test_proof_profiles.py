import unittest

from core.proof_profiles import PROOF_PROFILES, assurance_claims, profile_spec


class ProofProfileRegistryTests(unittest.TestCase):
    def test_profiles_are_declarative_and_expose_assurance_claims(self):
        self.assertIn('integrity', PROOF_PROFILES)
        self.assertIn('authority_lifecycle', PROOF_PROFILES)
        self.assertEqual(assurance_claims('integrity'), ['signed_manifest', 'graph_integrity'])
        self.assertIn('independent_outcome_attestation', assurance_claims('authority_lifecycle'))
        self.assertIs(profile_spec('authority_lifecycle'), PROOF_PROFILES['authority_lifecycle'])

    def test_unknown_profile_has_no_assurance_claims(self):
        self.assertEqual(assurance_claims('does_not_exist'), [])
        self.assertIsNone(profile_spec('does_not_exist'))


if __name__ == '__main__':
    unittest.main()
