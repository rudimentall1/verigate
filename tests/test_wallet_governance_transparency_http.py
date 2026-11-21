import base64
import hashlib
import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.governance import GovernanceMember, GovernancePolicy, governor_id
from core.storage import Storage
from core.wallet_enrollment import WalletEnrollmentService, installation_principal
from core.wallet_governance_outbox import WalletGovernanceOutboxDispatcher
from core.wallet_governance_transparency import (
    WalletGovernanceTransparencyLog,
    verify_wallet_governance_transparency_bundle,
)
from core.wallet_governance_transparency_http import (
    WalletGovernanceTransparencyHTTPTransport,
    make_wallet_governance_log_handler,
)


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()


def approval(action, private_key, suffix):
    payload = {
        "governance_version": 1,
        "action_digest": hashlib.sha256(canonical(action)).hexdigest(),
        "governor_id": governor_id(private_key.public_key()),
        "role": "governor",
        "approval_id": f"approval-{suffix}-{action['action_id']}",
        "issued_at": time.time(),
        "expires_at": time.time() + 120,
        "nonce": f"nonce-{suffix}-{action['action_id']}",
    }
    return {
        "payload": payload,
        "signature": base64.b64encode(private_key.sign(canonical(payload))).decode(),
        "algorithm": "Ed25519",
    }


class WalletGovernanceTransparencyHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = WalletGovernanceTransparencyLog(
            Path(self.tmp.name) / "independent-http-log.db",
            log_id="wallet-governance-http-test",
            signing_key=Ed25519PrivateKey.generate(),
        )
        self.token = "test-bearer-token-" + "x" * 40
        handler = make_wallet_governance_log_handler(
            self.log,
            bearer_token=self.token,
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        self.thread.start()
        self.transport = WalletGovernanceTransparencyHTTPTransport(
            f"http://127.0.0.1:{self.server.server_port}",
            bearer_token=self.token,
            timeout=3,
        )
        self.principal = "anna-installation:" + "7" * 64

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.log.close()
        self.tmp.cleanup()

    def make_envelope(self, action_id="http-enroll-001"):
        return {
            "algorithm": "Ed25519-MULTIPARTY",
            "action": {
                "action_id": action_id,
                "action": "WALLET_ENROLL",
                "installation_principal": self.principal,
                "enrollment_id": "enrollment-http-001",
            },
            "approvals": [],
        }

    def test_http_transport_appends_and_verifies_signed_checkpoint(self):
        envelope = self.make_envelope()
        bundle = self.transport.append_envelope(self.principal, envelope)
        ok, reason, checks = verify_wallet_governance_transparency_bundle(
            bundle,
            history_envelopes=[envelope],
            installation_principal=self.principal,
            trusted_log_public_key_b64=self.log.public_key_b64,
            trusted_checkpoint_sha256=bundle["checkpoint"]["checkpoint_sha256"],
        )
        self.assertTrue(ok, reason)
        self.assertTrue(checks["wallet_governance_transparency_anchor"]["pinned"])
        self.assertEqual(bundle["checkpoint"]["payload"]["entry_count"], 1)

    def test_http_transport_retries_idempotently_after_unknown_response(self):
        envelope = self.make_envelope()
        first = self.transport.append_envelope(self.principal, envelope)
        second = self.transport.append_envelope(self.principal, envelope)

        self.assertEqual(first, second)
        self.assertEqual(second["checkpoint"]["payload"]["checkpoint_sequence"], 1)
        self.assertEqual(len(second["entries"]), 1)

    def test_http_client_rejects_oversized_envelope_before_network_send(self):
        envelope = self.make_envelope()
        envelope["action"]["reason"] = "x" * 1_100_000
        with self.assertRaisesRegex(ValueError, "size limit"):
            self.transport.append_envelope(self.principal, envelope)

    def test_http_endpoint_rejects_wrong_bearer_token(self):
        unauthorized = WalletGovernanceTransparencyHTTPTransport(
            f"http://127.0.0.1:{self.server.server_port}",
            bearer_token="wrong-token-" + "x" * 40,
            timeout=3,
        )
        with self.assertRaisesRegex(PermissionError, "authentication"):
            unauthorized.append_envelope(
                self.principal,
                self.make_envelope(),
            )
        with self.assertRaises(LookupError):
            self.log.export_bundle(self.principal)

    def test_http_endpoint_accepts_overlapping_tokens_during_rotation(self):
        rotated_handler = make_wallet_governance_log_handler(
            self.log,
            bearer_token="new-bearer-token-" + "n" * 40,
            previous_bearer_tokens=("old-bearer-token-" + "o" * 40,),
        )
        rotated_server = ThreadingHTTPServer(("127.0.0.1", 0), rotated_handler)
        rotated_server.daemon_threads = True
        rotated_thread = threading.Thread(
            target=rotated_server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        rotated_thread.start()
        try:
            old_client = WalletGovernanceTransparencyHTTPTransport(
                f"http://127.0.0.1:{rotated_server.server_port}",
                bearer_token="old-bearer-token-" + "o" * 40,
                timeout=3,
            )
            new_client = WalletGovernanceTransparencyHTTPTransport(
                f"http://127.0.0.1:{rotated_server.server_port}",
                bearer_token="new-bearer-token-" + "n" * 40,
                timeout=3,
            )
            rejected_client = WalletGovernanceTransparencyHTTPTransport(
                f"http://127.0.0.1:{rotated_server.server_port}",
                bearer_token="untrusted-bearer-token-" + "u" * 40,
                timeout=3,
            )
            old_envelope = self.make_envelope("rotation-old")
            old_envelope["action"]["enrollment_id"] = "enrollment-rotation-old"
            new_envelope = self.make_envelope("rotation-new")
            new_envelope["action"]["enrollment_id"] = "enrollment-rotation-new"
            rejected_envelope = self.make_envelope("rotation-rejected")
            rejected_envelope["action"]["enrollment_id"] = "enrollment-rotation-rejected"
            old_client.append_envelope(self.principal, old_envelope)
            new_client.append_envelope(self.principal, new_envelope)
            with self.assertRaisesRegex(PermissionError, "authentication"):
                rejected_client.append_envelope(self.principal, rejected_envelope)
        finally:
            rotated_server.shutdown()
            rotated_server.server_close()
            rotated_thread.join(timeout=3)

    def test_transport_requires_https_for_non_loopback_services(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            WalletGovernanceTransparencyHTTPTransport(
                "http://wallet-log.example.com",
                bearer_token=self.token,
            )

    def test_wallet_enrollment_apply_delivers_through_real_http_endpoint(self):
        storage = Storage(str(Path(self.tmp.name) / "verigate.db"))
        gov1 = Ed25519PrivateKey.generate()
        gov2 = Ed25519PrivateKey.generate()
        policy = GovernancePolicy(
            policy_id="http-wallet-outbox",
            version=1,
            threshold=2,
            members=(
                GovernanceMember.from_public_key(gov1.public_key(), "governor"),
                GovernanceMember.from_public_key(gov2.public_key(), "governor"),
            ),
            allowed_actions=("WALLET_ENROLL", "WALLET_REVOKE"),
        )
        issuer = Ed25519PrivateKey.generate()
        issuer_b64 = base64.b64encode(
            issuer.public_key().public_bytes_raw()
        ).decode()
        principal = installation_principal(issuer_b64)[0]
        dispatcher = WalletGovernanceOutboxDispatcher(
            storage,
            self.transport,
            trusted_log_public_key_b64=self.log.public_key_b64,
        )
        service = WalletEnrollmentService(
            storage,
            transparency_dispatcher=dispatcher,
        )
        try:
            action = service.build_action(
                action="WALLET_ENROLL",
                reason="operator verified wallet ownership",
                governance_policy_sha256=policy.digest,
                issuer_public_key_b64=issuer_b64,
                chain_id=8453,
                network="base",
                wallet_address="0x" + "c" * 40,
                min_confirmations=12,
            )
            result = service.apply(
                action,
                [
                    approval(action, gov1, "one"),
                    approval(action, gov2, "two"),
                ],
                policy,
            )
            self.assertEqual(result["status"], "APPLIED")
            self.assertEqual(result["transparency_delivery"]["status"], "DELIVERED")
            self.assertEqual(
                storage.wallet_governance_outbox_action_status(action["action_id"]),
                "DELIVERED",
            )
            self.assertEqual(
                storage.wallet_governance_transparency_bundle(principal)["checkpoint"]["payload"]["entry_count"],
                1,
            )
            verifier = service.evm_verifier_for_wallet(
                principal, 8453, "0x" + "c" * 40,
            )
            self.assertEqual(verifier.expected_sender, "0x" + "c" * 40)
        finally:
            storage.close()


if __name__ == "__main__":
    unittest.main()
