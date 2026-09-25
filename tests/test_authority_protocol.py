import unittest

from core.authority_protocol import (
    Authority,
    AuthorityRequest,
    AuthorityState,
    LifecycleStage,
    authority_ceiling_allows,
    canonical_digest,
)


class AuthorityProtocolTest(unittest.TestCase):
    def test_authority_digest_is_deterministic(self):
        authority = Authority(
            authority_id="auth-1",
            agent_id="agent-1",
            identity_id="id-1",
            capability_id="cap-1",
            capability_version=2,
            capability_sha256="cap-digest",
            state=AuthorityState.STANDARD,
            multiplier=0.75,
            epoch=3,
            evidence_refs=("ev-1", "ev-2"),
        )
        self.assertEqual(authority.digest, canonical_digest(authority.as_dict()))
        self.assertEqual(authority.as_dict()["state"], "STANDARD")

    def test_request_is_not_permission(self):
        request = AuthorityRequest(
            intent_id="intent-1",
            agent_id="agent-1",
            identity_id="id-1",
            requested_capability="cap-1",
            lifecycle_stage=LifecycleStage.PROPOSE,
        )
        self.assertEqual(request.as_dict()["lifecycle_stage"], "PROPOSE")
        self.assertNotEqual(request.digest, "")

    def test_dynamic_authority_cannot_exceed_static_ceiling(self):
        self.assertTrue(authority_ceiling_allows(100, 0.5, 50))
        self.assertFalse(authority_ceiling_allows(100, 0.5, 51))
        self.assertFalse(authority_ceiling_allows(100, 2.0, 150))
        self.assertFalse(authority_ceiling_allows(-1, 1.0, 0))


if __name__ == "__main__":
    unittest.main()
