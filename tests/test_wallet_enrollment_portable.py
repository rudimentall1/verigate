import base64
import hashlib
import importlib.util
import json
import tempfile
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.governance import GovernanceMember, GovernancePolicy, governor_id
from core.evidence import EvidenceGraph
from core.wallet_enrollment_history import resolve_portable_wallet_enrollment_history
from core.wallet_governance_transparency import WalletGovernanceTransparencyLog, verify_wallet_governance_transparency_bundle
from core.storage import Storage
from core.wallet_enrollment import WalletEnrollmentService


ROOT = Path(__file__).resolve().parents[1]
VERIFIER_PATH = ROOT / "tools" / "verigate_proof_verifier.py"
SPEC = importlib.util.spec_from_file_location("verigate_proof_verifier", VERIFIER_PATH)
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)

PACKAGE_VERIFIER_PATH = (
    ROOT / "packaging" / "verigate-verify" / "src"
    / "verigate_verify" / "_verifier.py"
)
PACKAGE_SPEC = importlib.util.spec_from_file_location(
    "verigate_verify_packaged_verifier", PACKAGE_VERIFIER_PATH,
)
PACKAGE_VERIFIER = importlib.util.module_from_spec(PACKAGE_SPEC)
PACKAGE_SPEC.loader.exec_module(PACKAGE_VERIFIER)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def governance_approval(action, private_key, suffix):
    issued_at = time.time()
    payload = {
        "governance_version": 1,
        "action_digest": digest(action),
        "governor_id": governor_id(private_key.public_key()),
        "role": "governor",
        "approval_id": f"approval-{suffix}-{action['action_id']}",
        "issued_at": issued_at,
        "expires_at": issued_at + 120,
        "nonce": f"nonce-{suffix}-{action['action_id']}",
    }
    return {
        "payload": payload,
        "signature": base64.b64encode(private_key.sign(canonical(payload))).decode(),
        "algorithm": "Ed25519",
    }


class PortableWalletGovernanceProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(str(Path(self.tmp.name) / "wallet.db"))
        self.gov1 = Ed25519PrivateKey.generate()
        self.gov2 = Ed25519PrivateKey.generate()
        self.policy = GovernancePolicy(
            policy_id="portable-wallet-governance",
            version=1,
            threshold=2,
            members=(
                GovernanceMember.from_public_key(self.gov1.public_key(), "governor"),
                GovernanceMember.from_public_key(self.gov2.public_key(), "governor"),
            ),
            allowed_actions=("WALLET_ENROLL", "WALLET_REVOKE"),
        )
        self.issuer = Ed25519PrivateKey.generate()
        self.issuer_b64 = base64.b64encode(
            self.issuer.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw,
            )
        ).decode()
        self.principal = "anna-installation:" + hashlib.sha256(
            self.issuer.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw,
            )
        ).hexdigest()
        self.wallet = "0x" + "a" * 40
        self.service = WalletEnrollmentService(self.storage)

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def make_graph(self, *, include_revoke=True, rewrite_snapshot=False):
        enroll = self.service.build_action(
            action="WALLET_ENROLL",
            reason="operator verified wallet ownership",
            governance_policy_sha256=self.policy.digest,
            issuer_public_key_b64=self.issuer_b64,
            chain_id=8453,
            network="base",
            wallet_address=self.wallet,
            min_confirmations=12,
        )
        enroll_approvals = [
            governance_approval(enroll, self.gov1, "enroll-one"),
            governance_approval(enroll, self.gov2, "enroll-two"),
        ]
        self.service.apply(enroll, enroll_approvals, self.policy)
        enroll_effective_at = max(
            [enroll["issued_at"], *(item["payload"]["issued_at"] for item in enroll_approvals)]
        )

        revoke = None
        revoke_approvals = []
        if include_revoke:
            time.sleep(0.003)
            revoke = self.service.build_action(
                action="WALLET_REVOKE",
                reason="wallet decommissioned",
                governance_policy_sha256=self.policy.digest,
                enrollment_id=enroll["enrollment_id"],
            )
            revoke_approvals = [
                governance_approval(revoke, self.gov1, "revoke-one"),
                governance_approval(revoke, self.gov2, "revoke-two"),
            ]
            self.service.apply(revoke, revoke_approvals, self.policy)

        enrollment = self.storage.wallet_enrollment(enroll["enrollment_id"])
        if rewrite_snapshot:
            # Model a coordinated database rollback: remove the revoke envelope
            # and rewrite the mutable registry row back to ACTIVE.
            enrollment["status"] = "ACTIVE"
            enrollment["revoked_at"] = None
        full_history = sorted(
            self.storage.wallet_enrollment_governance_actions(self.principal),
            key=lambda item: item["action"]["action_id"],
        )
        trusted_history_sha256 = digest(full_history)
        history = full_history
        if not include_revoke or rewrite_snapshot:
            history = [item for item in history if item["action"]["action"] != "WALLET_REVOKE"]
        history_data = {
            "installation_principal": self.principal,
            "envelopes": history,
            "history_sha256": digest(history),
        }
        payload = {
            "agent_id": self.principal,
            "nodes": [
                {
                    "type": "wallet_enrollment",
                    "id": enrollment["enrollment_id"],
                    "data": enrollment,
                    "sha256": digest(enrollment),
                },
                {
                    "type": "wallet_enrollment_governance_history",
                    "id": self.principal,
                    "data": history_data,
                    "sha256": digest(history_data),
                },
            ],
            "edges": [
                {
                    "from": f"wallet_enrollment_governance_history:{self.principal}",
                    "relation": "COVERS",
                    "to": f"wallet_enrollment:{enrollment['enrollment_id']}",
                }
            ],
        }
        return (
            payload, enroll_effective_at, revoke, revoke_approvals,
            trusted_history_sha256 if rewrite_snapshot else history_data["history_sha256"],
        )

    def verify(self, payload, *, attested_at, history_sha, policy_digests=None):
        return VERIFIER.verify_wallet_enrollment_history(
            payload,
            installation_principal=self.principal,
            chain_id=8453,
            wallet_address=self.wallet,
            attested_at=attested_at,
            trusted_policy_digests=policy_digests,
            trusted_history_digests={history_sha},
        )

    def test_core_resolver_accepts_pinned_history_and_resolves_pre_revoke_state(self):
        payload, enrolled_at, revoke, approvals, history_sha = self.make_graph()
        history_node = next(
            item for item in payload["nodes"]
            if item["type"] == "wallet_enrollment_governance_history"
        )
        enrollment_nodes = [
            item["data"] for item in payload["nodes"]
            if item["type"] == "wallet_enrollment"
        ]
        revoke_effective_at = max(
            [revoke["issued_at"], *(item["payload"]["issued_at"] for item in approvals)]
        )
        ok, reason, enrollment, checks = resolve_portable_wallet_enrollment_history(
            history_node["data"],
            enrollment_nodes,
            installation_principal=self.principal,
            chain_id=8453,
            wallet_address=self.wallet,
            attested_at=(enrolled_at + revoke_effective_at) / 2,
            trusted_policy_digests={self.policy.digest},
            trusted_history_digests={history_sha},
        )
        self.assertTrue(ok, reason)
        self.assertEqual(enrollment["status"], "ACTIVE")
        self.assertTrue(checks["wallet_enrollment_history_anchor"]["pinned"])

    def test_evidence_graph_builder_embeds_independent_wallet_transparency_checkpoint(self):
        enroll = self.service.build_action(
            action="WALLET_ENROLL",
            reason="operator verified wallet ownership",
            governance_policy_sha256=self.policy.digest,
            issuer_public_key_b64=self.issuer_b64,
            chain_id=8453,
            network="base",
            wallet_address=self.wallet,
            min_confirmations=12,
        )
        self.service.apply(
            enroll,
            [
                governance_approval(enroll, self.gov1, "anchor-one"),
                governance_approval(enroll, self.gov2, "anchor-two"),
            ],
            self.policy,
        )
        envelopes = self.storage.wallet_enrollment_governance_actions(self.principal)
        log_key = Ed25519PrivateKey.generate()
        log = WalletGovernanceTransparencyLog(
            Path(self.tmp.name) / "external-log.db",
            log_id="independent-wallet-log",
            signing_key=log_key,
        )
        try:
            bundle = log.checkpoint_history(self.principal, envelopes)
            graph = EvidenceGraph(
                self.storage,
                self.issuer.public_key(),
                wallet_governance_anchors={self.principal: bundle},
            )
            receipt = {
                "payload": {
                    "receipt_id": "anchored-chain-receipt",
                    "submission_data": {
                        "chain_id": 8453,
                        "sender": self.wallet,
                        "network": "base",
                    },
                }
            }
            nodes, edges, verification = [], [], {}
            graph._add_wallet_enrollment_evidence(
                principal=self.principal,
                receipt=receipt,
                nodes=nodes,
                edges=edges,
                verification=verification,
            )
            anchor_node = next(
                item for item in nodes
                if item["type"] == "wallet_governance_transparency_log"
            )
            history_node = next(
                item for item in nodes
                if item["type"] == "wallet_enrollment_governance_history"
            )
            self.assertEqual(
                anchor_node["id"],
                bundle["checkpoint"]["checkpoint_sha256"],
            )
            self.assertIn(
                {
                    "from": f"wallet_enrollment_governance_history:{self.principal}",
                    "relation": "ANCHORED_BY",
                    "to": f"wallet_governance_transparency_log:{anchor_node['id']}",
                },
                edges,
            )
            ok, reason, checks = verify_wallet_governance_transparency_bundle(
                anchor_node["data"],
                history_envelopes=history_node["data"]["envelopes"],
                installation_principal=self.principal,
                trusted_log_public_key_b64=base64.b64encode(
                    log_key.public_key().public_bytes(
                        serialization.Encoding.Raw,
                        serialization.PublicFormat.Raw,
                    )
                ).decode(),
                trusted_checkpoint_sha256=bundle["checkpoint"]["checkpoint_sha256"],
            )
            self.assertTrue(ok, reason)
            self.assertTrue(checks["wallet_governance_transparency_anchor"]["pinned"])
            self.assertTrue(
                verification[f"wallet_governance_transparency:{self.principal}"]["valid"]
            )
        finally:
            log.close()

    def test_evidence_graph_builder_exports_complete_wallet_history_and_receipt_binding(self):
        enroll = self.service.build_action(
            action="WALLET_ENROLL",
            reason="operator verified wallet ownership",
            governance_policy_sha256=self.policy.digest,
            issuer_public_key_b64=self.issuer_b64,
            chain_id=8453,
            network="base",
            wallet_address=self.wallet,
            min_confirmations=12,
        )
        self.service.apply(
            enroll,
            [
                governance_approval(enroll, self.gov1, "builder-one"),
                governance_approval(enroll, self.gov2, "builder-two"),
            ],
            self.policy,
        )
        receipt = {
            "payload": {
                "receipt_id": "portable-chain-receipt",
                "submission_data": {
                    "chain_id": 8453,
                    "sender": self.wallet,
                    "network": "base",
                },
            }
        }
        nodes, edges, verification = [], [], {}
        EvidenceGraph(self.storage, self.issuer.public_key())._add_wallet_enrollment_evidence(
            principal=self.principal,
            receipt=receipt,
            nodes=nodes,
            edges=edges,
            verification=verification,
        )
        graph = EvidenceGraph(self.storage, self.issuer.public_key())
        enrolled_key = graph._wallet_enrollment_issuer_key(
            principal=self.principal, receipt=receipt,
        )
        self.assertEqual(
            enrolled_key.public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw,
            ),
            self.issuer.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw,
            ),
        )
        history = next(
            item for item in nodes
            if item["type"] == "wallet_enrollment_governance_history"
        )
        enrollment = next(
            item for item in nodes if item["type"] == "wallet_enrollment"
        )
        self.assertEqual(history["data"]["history_sha256"], digest(history["data"]["envelopes"]))
        self.assertEqual(
            sum(1 for item in history["data"]["envelopes"] if item["action"]["action"] == "WALLET_ENROLL"),
            1,
        )
        self.assertIn(
            {
                "from": f"wallet_enrollment_governance_history:{self.principal}",
                "relation": "COVERS",
                "to": f"wallet_enrollment:{enrollment['id']}",
            },
            edges,
        )
        self.assertIn(
            {
                "from": f"wallet_enrollment:{enrollment['id']}",
                "relation": "AUTHORIZES_RECEIPT",
                "to": "execution_receipt:portable-chain-receipt",
            },
            edges,
        )
        self.assertTrue(verification[f"wallet_enrollment:{self.principal}"]["valid"])

    def test_packaged_verifier_matches_wallet_history_trust_contract(self):
        payload, enrolled_at, _, _, history_sha = self.make_graph(include_revoke=False)
        kwargs = {
            "installation_principal": self.principal,
            "chain_id": 8453,
            "wallet_address": self.wallet,
            "attested_at": enrolled_at + 1,
            "trusted_policy_digests": {self.policy.digest},
            "trusted_history_digests": {history_sha},
        }
        tool_result = VERIFIER.verify_wallet_enrollment_history(payload, **kwargs)
        package_result = PACKAGE_VERIFIER.verify_wallet_enrollment_history(payload, **kwargs)
        self.assertEqual(package_result, tool_result)
        self.assertTrue(package_result[0], package_result[1])

    def test_portable_proof_replays_revoke_after_attestation_without_retroactive_invalidation(self):
        payload, enrolled_at, revoke, approvals, history_sha = self.make_graph()
        self.assertIsNotNone(revoke)
        revoke_effective_at = max(
            [revoke["issued_at"], *(item["payload"]["issued_at"] for item in approvals)]
        )
        ok, reason, enrollment, checks = self.verify(
            payload,
            attested_at=(enrolled_at + revoke_effective_at) / 2,
            history_sha=history_sha,
            policy_digests={self.policy.digest},
        )
        self.assertTrue(ok, reason)
        self.assertEqual(enrollment["status"], "ACTIVE")
        self.assertTrue(checks["wallet_enrollment_history_anchor"]["pinned"])
        self.assertTrue(checks["wallet_governance_policy_trust_anchor"]["pinned"])

        ok_after, reason_after, _, _ = self.verify(
            payload,
            attested_at=revoke_effective_at + 1,
            history_sha=history_sha,
            policy_digests={self.policy.digest},
        )
        self.assertFalse(ok_after)
        self.assertIn("active", reason_after.lower())

    def test_portable_proof_requires_every_enrollment_snapshot_to_be_covered(self):
        payload, enrolled_at, _, _, history_sha = self.make_graph(include_revoke=False)
        payload["edges"] = []
        ok, reason, _, _ = self.verify(
            payload,
            attested_at=enrolled_at + 1,
            history_sha=history_sha,
            policy_digests={self.policy.digest},
        )
        self.assertFalse(ok)
        self.assertIn("covered", reason.lower())

    def test_portable_proof_rejects_untrusted_wallet_governance_policy(self):
        payload, enrolled_at, _, _, history_sha = self.make_graph(include_revoke=False)
        ok, reason, _, checks = self.verify(
            payload,
            attested_at=enrolled_at + 1,
            history_sha=history_sha,
            policy_digests={"0" * 64},
        )
        self.assertFalse(ok)
        self.assertIn("trusted", reason.lower())
        self.assertFalse(checks["wallet_governance_policy_trust_anchor"]["valid"])

    def test_portable_proof_reports_unpinned_wallet_governance_policy(self):
        payload, enrolled_at, _, _, history_sha = self.make_graph(include_revoke=False)
        ok, reason, enrollment, checks = VERIFIER.verify_wallet_enrollment_history(
            payload,
            installation_principal=self.principal,
            chain_id=8453,
            wallet_address=self.wallet,
            attested_at=enrolled_at + 1,
        )
        self.assertTrue(ok, reason)
        self.assertEqual(enrollment["status"], "ACTIVE")
        self.assertFalse(checks["wallet_governance_policy_trust_anchor"]["pinned"])
        self.assertFalse(checks["wallet_enrollment_history_anchor"]["pinned"])

    def test_external_history_pin_detects_coordinated_revoke_and_snapshot_rollback(self):
        payload, enrolled_at, _, _, history_sha = self.make_graph(
            include_revoke=True, rewrite_snapshot=True,
        )
        ok, reason, _, checks = self.verify(
            payload,
            attested_at=enrolled_at + 10,
            history_sha=history_sha,
            policy_digests={self.policy.digest},
        )
        self.assertFalse(ok)
        self.assertIn("history", reason.lower())
        self.assertFalse(checks["wallet_enrollment_history_anchor"]["valid"])

    def test_portable_proof_rejects_tampered_governance_approval(self):
        payload, enrolled_at, _, _, history_sha = self.make_graph(include_revoke=False)
        history_node = next(
            item for item in payload["nodes"]
            if item["type"] == "wallet_enrollment_governance_history"
        )
        history_node["data"]["envelopes"][0]["approvals"][0]["signature"] = base64.b64encode(
            b"\x00" * 64
        ).decode()
        history_node["data"]["history_sha256"] = digest(
            history_node["data"]["envelopes"]
        )
        history_node["sha256"] = digest(history_node["data"])
        ok, reason, _, _ = self.verify(
            payload,
            attested_at=enrolled_at + 1,
            history_sha=history_node["data"]["history_sha256"],
            policy_digests={self.policy.digest},
        )
        self.assertFalse(ok)
        self.assertTrue(
            "quorum" in reason.lower() or "signature" in reason.lower(),
            reason,
        )


if __name__ == "__main__":
    unittest.main()
