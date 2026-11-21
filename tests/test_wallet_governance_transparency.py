import base64
import hashlib
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.wallet_governance_transparency import (
    WalletGovernanceTransparencyLog,
    verify_wallet_governance_transparency_bundle,
)


TOOL_VERIFIER_PATH = Path(__file__).resolve().parents[1] / "tools" / "verigate_proof_verifier.py"
TOOL_SPEC = importlib.util.spec_from_file_location(
    "verigate_transparency_tool_verifier", TOOL_VERIFIER_PATH,
)
TOOL_VERIFIER = importlib.util.module_from_spec(TOOL_SPEC)
TOOL_SPEC.loader.exec_module(TOOL_VERIFIER)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class WalletGovernanceTransparencyLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "independent-wallet-transparency.sqlite3"
        self.signing_key = Ed25519PrivateKey.generate()
        self.public_key_b64 = base64.b64encode(
            self.signing_key.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        ).decode()
        self.principal = "anna-installation:" + "1" * 64
        self.log = WalletGovernanceTransparencyLog(
            self.path,
            log_id="anna-independent-governance-log",
            signing_key=self.signing_key,
        )
        self.enroll = {
            "algorithm": "Ed25519-MULTIPARTY",
            "action": {
                "action_id": "action-enroll-001",
                "action": "WALLET_ENROLL",
                "installation_principal": "anna-installation:" + "1" * 64,
                "enrollment_id": "enrollment-001",
            },
            "approvals": [{"payload": {"approval_id": "approval-enroll"}}],
        }
        self.revoke = {
            "algorithm": "Ed25519-MULTIPARTY",
            "action": {
                "action_id": "action-revoke-002",
                "action": "WALLET_REVOKE",
                "enrollment_id": "enrollment-001",
            },
            "approvals": [{"payload": {"approval_id": "approval-revoke"}}],
        }

    def tearDown(self):
        self.log.close()
        self.tmp.cleanup()

    def verify(self, bundle, envelopes, expected_checkpoint_sha256, trusted_key=None):
        return verify_wallet_governance_transparency_bundle(
            bundle,
            history_envelopes=envelopes,
            installation_principal=self.principal,
            trusted_log_public_key_b64=trusted_key,
            trusted_checkpoint_sha256=expected_checkpoint_sha256,
        )

    def test_standalone_verifier_matches_core_transparency_verifier(self):
        bundle = self.log.checkpoint_history(
            self.principal, [self.enroll, self.revoke],
        )
        arguments = {
            "history_envelopes": [self.enroll, self.revoke],
            "installation_principal": self.principal,
            "trusted_log_public_key_b64": self.public_key_b64,
            "trusted_checkpoint_sha256": bundle["checkpoint"]["checkpoint_sha256"],
        }
        core_result = verify_wallet_governance_transparency_bundle(bundle, **arguments)
        standalone_result = TOOL_VERIFIER.verify_wallet_governance_transparency_bundle(
            bundle, **arguments,
        )
        self.assertEqual(standalone_result, core_result)
        self.assertTrue(standalone_result[0], standalone_result[1])

    def test_checkpoint_commits_complete_history_through_signed_append_only_chain(self):
        bundle = self.log.checkpoint_history(self.principal, [self.enroll, self.revoke])

        self.assertEqual(bundle["checkpoint"]["payload"]["entry_count"], 2)
        self.assertEqual(
            bundle["entries"][0]["payload"]["previous_entry_sha256"],
            "0" * 64,
        )
        self.assertEqual(
            bundle["entries"][1]["payload"]["previous_entry_sha256"],
            bundle["entries"][0]["entry_sha256"],
        )
        self.assertEqual(
            bundle["checkpoint"]["payload"]["head_entry_sha256"],
            bundle["entries"][-1]["entry_sha256"],
        )

        ok, reason, checks = self.verify(
            bundle,
            [self.enroll, self.revoke],
            bundle["checkpoint"]["checkpoint_sha256"],
            self.public_key_b64,
        )
        self.assertTrue(ok, reason)
        self.assertTrue(checks["wallet_governance_transparency_anchor"]["pinned"])
        self.assertTrue(checks["wallet_governance_transparency_signature"]["valid"])

    def test_external_log_can_ingest_governance_actions_one_at_a_time(self):
        first = self.log.append_envelope(self.principal, self.enroll)
        second = self.log.append_envelope(self.principal, self.revoke)
        retry = self.log.append_envelope(self.principal, self.revoke)

        self.assertEqual(first["checkpoint"]["payload"]["entry_count"], 1)
        self.assertEqual(second["checkpoint"]["payload"]["entry_count"], 2)
        self.assertEqual(
            second["checkpoint"]["payload"]["previous_checkpoint_sha256"],
            first["checkpoint"]["checkpoint_sha256"],
        )
        self.assertEqual(second, retry)

        rewritten = json.loads(json.dumps(self.revoke))
        rewritten["reason"] = "altered revoke"
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.log.append_envelope(self.principal, rewritten)

    def test_checkpointing_same_history_is_idempotent_and_does_not_advance_sequence(self):
        first = self.log.checkpoint_history(self.principal, [self.enroll])
        second = self.log.checkpoint_history(self.principal, [self.enroll])

        self.assertEqual(first, second)
        self.assertEqual(second["checkpoint"]["payload"]["checkpoint_sequence"], 1)

    def test_public_key_export_produces_pem_usable_by_offline_verifier(self):
        public_path = self.log.export_public_key_pem(
            Path(self.tmp.name) / "trust" / "wallet-log.pub.pem",
        )
        public_key = serialization.load_pem_public_key(public_path.read_bytes())
        exported_raw = public_key.public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        expected_raw = self.signing_key.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        self.assertEqual(exported_raw, expected_raw)

    def test_new_history_advances_entry_and_checkpoint_chains(self):
        first = self.log.checkpoint_history(self.principal, [self.enroll])
        second = self.log.checkpoint_history(self.principal, [self.enroll, self.revoke])

        self.assertEqual(second["checkpoint"]["payload"]["checkpoint_sequence"], 2)
        self.assertEqual(
            second["checkpoint"]["payload"]["previous_checkpoint_sha256"],
            first["checkpoint"]["checkpoint_sha256"],
        )
        self.assertEqual(len(second["entries"]), 2)

    def test_checkpoint_rejects_omitted_or_rewritten_previously_logged_action(self):
        self.log.checkpoint_history(self.principal, [self.enroll, self.revoke])

        with self.assertRaisesRegex(ValueError, "omits"):
            self.log.checkpoint_history(self.principal, [self.enroll])

        rewritten = dict(self.enroll)
        rewritten["reason"] = "rewritten after anchoring"
        with self.assertRaisesRegex(ValueError, "immutable"):
            self.log.checkpoint_history(self.principal, [rewritten, self.revoke])

    def test_sqlite_append_only_triggers_reject_updates_and_deletes(self):
        self.log.checkpoint_history(self.principal, [self.enroll])
        connection = sqlite3.connect(self.path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE wallet_governance_log_entries SET envelope_json = '{}' "
                    "WHERE installation_principal = ?",
                    (self.principal,),
                )
            connection.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM wallet_governance_log_checkpoints WHERE installation_principal = ?",
                    (self.principal,),
                )
            connection.rollback()
            entry = connection.execute(
                "SELECT installation_principal, sequence, log_id, action_id, entry_sha256, "
                "entry_payload_json, envelope_json FROM wallet_governance_log_entries "
                "WHERE installation_principal = ?",
                (self.principal,),
            ).fetchone()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT OR REPLACE INTO wallet_governance_log_entries "
                    "(installation_principal, sequence, log_id, action_id, entry_sha256, "
                    "entry_payload_json, envelope_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    entry,
                )
            connection.rollback()
        finally:
            connection.close()

    def test_verifier_rejects_stale_checkpoint_when_latest_checkpoint_is_trusted(self):
        old_bundle = self.log.checkpoint_history(self.principal, [self.enroll])
        latest_bundle = self.log.checkpoint_history(
            self.principal, [self.enroll, self.revoke],
        )

        ok, reason, checks = self.verify(
            old_bundle,
            [self.enroll],
            latest_bundle["checkpoint"]["checkpoint_sha256"],
            self.public_key_b64,
        )
        self.assertFalse(ok)
        self.assertIn("checkpoint", reason.lower())
        self.assertFalse(checks["wallet_governance_transparency_anchor"]["valid"])

    def test_verifier_rejects_untrusted_log_key_and_wrong_checkpoint_digest(self):
        bundle = self.log.checkpoint_history(self.principal, [self.enroll])
        other_key = Ed25519PrivateKey.generate()
        other_b64 = base64.b64encode(
            other_key.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        ).decode()

        wrong_key_ok, wrong_key_reason, _ = self.verify(
            bundle,
            [self.enroll],
            bundle["checkpoint"]["checkpoint_sha256"],
            other_b64,
        )
        self.assertFalse(wrong_key_ok)
        self.assertIn("key", wrong_key_reason.lower())

        wrong_hash_ok, wrong_hash_reason, _ = self.verify(
            bundle,
            [self.enroll],
            "0" * 64,
            self.public_key_b64,
        )
        self.assertFalse(wrong_hash_ok)
        self.assertIn("checkpoint", wrong_hash_reason.lower())

    def test_verifier_rejects_non_finite_checkpoint_time_and_malformed_signer_key(self):
        bundle = self.log.checkpoint_history(self.principal, [self.enroll])
        overflow = json.loads(json.dumps(bundle))
        overflow["checkpoint"]["payload"]["issued_at"] = 10 ** 400
        overflow["checkpoint"]["checkpoint_sha256"] = digest(
            overflow["checkpoint"]["payload"]
        )
        ok, reason, _ = verify_wallet_governance_transparency_bundle(
            overflow,
            history_envelopes=[self.enroll],
            installation_principal=self.principal,
        )
        self.assertFalse(ok)
        self.assertIn("checkpoint", reason.lower())

        malformed_key = json.loads(json.dumps(bundle))
        malformed_key["checkpoint"]["signer_public_key_b64"] = "%%%not-base64%%%"
        malformed_ok, malformed_reason, _ = verify_wallet_governance_transparency_bundle(
            malformed_key,
            history_envelopes=[self.enroll],
            installation_principal=self.principal,
        )
        self.assertFalse(malformed_ok)
        self.assertIn("base64", malformed_reason.lower())

    def test_verifier_rejects_truncated_or_reordered_log_entries(self):
        bundle = self.log.checkpoint_history(
            self.principal, [self.enroll, self.revoke],
        )
        truncated = dict(bundle)
        truncated["entries"] = bundle["entries"][:1]
        ok, reason, _ = self.verify(
            truncated,
            [self.enroll, self.revoke],
            bundle["checkpoint"]["checkpoint_sha256"],
            self.public_key_b64,
        )
        self.assertFalse(ok)
        self.assertIn("chain", reason.lower())

        reordered = dict(bundle)
        reordered["entries"] = list(reversed(bundle["entries"]))
        reordered_ok, reordered_reason, _ = self.verify(
            reordered,
            [self.enroll, self.revoke],
            bundle["checkpoint"]["checkpoint_sha256"],
            self.public_key_b64,
        )
        self.assertFalse(reordered_ok)
        self.assertIn("sequence", reordered_reason.lower())

    def test_verifier_reports_unpinned_external_log_when_no_out_of_band_anchor_is_given(self):
        bundle = self.log.checkpoint_history(self.principal, [self.enroll])
        ok, reason, checks = self.verify(
            bundle,
            [self.enroll],
            None,
            None,
        )
        self.assertTrue(ok, reason)
        self.assertFalse(checks["wallet_governance_transparency_anchor"]["pinned"])

    def test_checkpoint_rejects_malformed_installation_scope(self):
        with self.assertRaisesRegex(ValueError, "principal"):
            self.log.checkpoint_history("not-an-installation-principal", [self.enroll])

    def test_log_keeps_installation_principals_in_separate_entry_chains(self):
        other_principal = "anna-installation:" + "2" * 64
        primary = self.log.checkpoint_history(self.principal, [self.enroll])
        other = self.log.checkpoint_history(other_principal, [self.revoke])

        self.assertEqual(primary["entries"][0]["payload"]["sequence"], 1)
        self.assertEqual(other["entries"][0]["payload"]["sequence"], 1)
        self.assertEqual(
            primary["entries"][0]["entry_sha256"],
            other["entries"][0]["entry_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
