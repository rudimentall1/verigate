import base64
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.governance import GovernanceMember, GovernancePolicy, governor_id
from core.evidence import EvidenceGraph
from core.storage import Storage
from core.wallet_enrollment import WalletEnrollmentService, installation_principal
from core.wallet_governance_transparency import WalletGovernanceTransparencyLog
from core.wallet_governance_outbox import WalletGovernanceOutboxDispatcher


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


class LoseFirstResponse:
    """Simulate a timeout after the remote log committed an append."""

    def __init__(self, log):
        self.log = log
        self.calls = 0

    def append_envelope(self, installation_principal, envelope):
        self.calls += 1
        bundle = self.log.append_envelope(installation_principal, envelope)
        if self.calls == 1:
            raise TimeoutError("connection dropped after remote commit")
        return bundle


class AlwaysFailTransport:
    def append_envelope(self, installation_principal, envelope):
        raise ConnectionError("transparency log unavailable")


class WalletGovernanceTransactionalOutboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.storage = Storage(str(root / "verigate.db"))
        self.external_log = WalletGovernanceTransparencyLog(
            root / "independent-log" / "wallet-log.db",
            log_id="independent-wallet-governance",
            signing_key=Ed25519PrivateKey.generate(),
        )
        self.log_public_key_b64 = self.external_log.public_key_b64
        self.gov1 = Ed25519PrivateKey.generate()
        self.gov2 = Ed25519PrivateKey.generate()
        self.policy = GovernancePolicy(
            policy_id="wallet-outbox-test",
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
            self.issuer.public_key().public_bytes_raw()
        ).decode()
        self.principal = installation_principal(self.issuer_b64)[0]
        self.wallet = "0x" + "b" * 40

    def tearDown(self):
        self.external_log.close()
        self.storage.close()
        self.tmp.cleanup()

    def approvals(self, action):
        return [
            approval(action, self.gov1, "one"),
            approval(action, self.gov2, "two"),
        ]

    def make_enroll(self, service):
        return service.build_action(
            action="WALLET_ENROLL",
            reason="operator verified wallet ownership",
            governance_policy_sha256=self.policy.digest,
            issuer_public_key_b64=self.issuer_b64,
            chain_id=8453,
            network="base",
            wallet_address=self.wallet,
            min_confirmations=12,
        )

    def make_dispatcher(self, transport=None):
        return WalletGovernanceOutboxDispatcher(
            self.storage,
            transport or self.external_log,
            trusted_log_public_key_b64=self.log_public_key_b64,
        )

    def test_wallet_remains_unusable_until_external_log_acknowledges_action(self):
        transport = LoseFirstResponse(self.external_log)
        dispatcher = self.make_dispatcher(transport)
        service = WalletEnrollmentService(
            self.storage,
            transparency_dispatcher=dispatcher,
        )
        action = self.make_enroll(service)
        result = service.apply(action, self.approvals(action), self.policy)

        self.assertEqual(result["status"], "PENDING_TRANSPARENCY")
        self.assertEqual(result["transparency_delivery"]["status"], "PENDING")
        self.assertEqual(
            self.storage.wallet_governance_outbox_action_status(action["action_id"]),
            "PENDING",
        )
        enrollment = result["enrollment"]
        self.assertEqual(enrollment["status"], "ACTIVE")
        with self.assertRaisesRegex(PermissionError, "external transparency"):
            service.evm_verifier_for_wallet(
                self.principal, 8453, self.wallet,
            )

        retry = dispatcher.dispatch_pending(self.principal)
        self.assertEqual(len(retry), 1)
        self.assertTrue(retry[0]["delivered"], retry[0].get("reason"))
        self.assertEqual(
            self.storage.wallet_governance_outbox_action_status(action["action_id"]),
            "DELIVERED",
        )
        verifier = service.evm_verifier_for_wallet(self.principal, 8453, self.wallet)
        self.assertEqual(verifier.expected_sender, self.wallet)
        self.assertEqual(verifier.min_confirmations, 12)
        self.assertEqual(transport.calls, 2)

        bundle = self.storage.wallet_governance_transparency_bundle(self.principal)
        self.assertEqual(bundle["checkpoint"]["payload"]["entry_count"], 1)
        self.assertEqual(bundle["entries"][0]["payload"]["action_id"], action["action_id"])

    def test_governance_action_and_outbox_record_are_committed_atomically(self):
        service = WalletEnrollmentService(self.storage)
        action = self.make_enroll(service)
        result = service.apply(action, self.approvals(action), self.policy)

        self.assertEqual(result["status"], "PENDING_TRANSPARENCY")
        events = self.storage.wallet_governance_outbox_events(self.principal)
        history = self.storage.wallet_enrollment_governance_actions(self.principal)
        self.assertEqual(len(events), 1)
        self.assertEqual(len(history), 1)
        self.assertEqual(events[0]["action_id"], action["action_id"])
        self.assertEqual(events[0]["envelope"], history[0])
        self.assertEqual(events[0]["status"], "PENDING")

    def test_unavailable_log_keeps_durable_pending_action_and_blocks_verifier(self):
        dispatcher = self.make_dispatcher(AlwaysFailTransport())
        service = WalletEnrollmentService(
            self.storage,
            transparency_dispatcher=dispatcher,
        )
        action = self.make_enroll(service)
        result = service.apply(action, self.approvals(action), self.policy)

        self.assertEqual(result["status"], "PENDING_TRANSPARENCY")
        event = self.storage.wallet_governance_outbox_event(action["action_id"])
        self.assertEqual(event["status"], "PENDING")
        self.assertGreaterEqual(event["attempts"], 1)
        self.assertIn("unavailable", event["last_error"])
        self.assertIsNone(event["delivered_at"])
        with self.assertRaises(PermissionError):
            service.evm_verifier_for_wallet(self.principal, 8453, self.wallet)

    def test_revoke_is_locally_effective_while_external_delivery_retries(self):
        transport = LoseFirstResponse(self.external_log)
        dispatcher = self.make_dispatcher(transport)
        service = WalletEnrollmentService(
            self.storage,
            transparency_dispatcher=dispatcher,
        )
        enroll = self.make_enroll(service)
        enrolled = service.apply(
            enroll, self.approvals(enroll), self.policy,
        )["enrollment"]
        # The simulated transport drops only its first response; the initial
        # enrollment is already delivered on the first dispatcher attempt.
        self.assertEqual(
            self.storage.wallet_governance_outbox_action_status(enroll["action_id"]),
            "PENDING",
        )
        dispatcher.dispatch_pending(self.principal)
        self.assertEqual(
            self.storage.wallet_governance_outbox_action_status(enroll["action_id"]),
            "DELIVERED",
        )

        revoke = service.build_action(
            action="WALLET_REVOKE",
            reason="wallet compromise response",
            governance_policy_sha256=self.policy.digest,
            enrollment_id=enrolled["enrollment_id"],
        )
        result = service.apply(revoke, self.approvals(revoke), self.policy)
        self.assertEqual(result["enrollment"]["status"], "REVOKED")
        self.assertEqual(
            self.storage.wallet_governance_outbox_action_status(revoke["action_id"]),
            "DELIVERED",
        )
        with self.assertRaises(PermissionError):
            service.evm_verifier_for_wallet(self.principal, 8453, self.wallet)
        bundle = self.storage.wallet_governance_transparency_bundle(self.principal)
        self.assertEqual(bundle["checkpoint"]["payload"]["entry_count"], 2)

    def test_evidence_graph_uses_latest_acknowledged_outbox_checkpoint(self):
        dispatcher = self.make_dispatcher()
        service = WalletEnrollmentService(
            self.storage,
            transparency_dispatcher=dispatcher,
        )
        action = self.make_enroll(service)
        result = service.apply(action, self.approvals(action), self.policy)
        self.assertEqual(result["status"], "APPLIED")

        graph = EvidenceGraph(self.storage, self.issuer.public_key())
        receipt = {
            "payload": {
                "receipt_id": "outbox-receipt",
                "submission_data": {
                    "chain_id": 8453,
                    "sender": self.wallet,
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
        self.assertEqual(
            anchor_node["id"],
            self.storage.wallet_governance_transparency_bundle(
                self.principal,
            )["checkpoint"]["checkpoint_sha256"],
        )
        self.assertTrue(
            verification[f"wallet_governance_transparency:{self.principal}"]["valid"]
        )

    def test_dispatcher_preserves_local_acceptance_order_and_is_idempotent(self):
        dispatcher = self.make_dispatcher()
        service = WalletEnrollmentService(self.storage)
        enroll = self.make_enroll(service)
        enrolled = service.apply(
            enroll, self.approvals(enroll), self.policy,
        )["enrollment"]
        revoke = service.build_action(
            action="WALLET_REVOKE",
            reason="retire wallet",
            governance_policy_sha256=self.policy.digest,
            enrollment_id=enrolled["enrollment_id"],
        )
        service.apply(revoke, self.approvals(revoke), self.policy)

        results = dispatcher.dispatch_pending(self.principal)
        self.assertEqual([item["action_id"] for item in results], [
            enroll["action_id"], revoke["action_id"],
        ])
        self.assertTrue(all(item["delivered"] for item in results))
        self.assertEqual(
            [entry["payload"]["action_id"] for entry in self.external_log.export_bundle(self.principal)["entries"]],
            [enroll["action_id"], revoke["action_id"]],
        )
        self.assertEqual(dispatcher.dispatch_pending(self.principal), [])

    def test_dispatcher_lease_excludes_concurrent_worker_and_is_released(self):
        service = WalletEnrollmentService(self.storage)
        action = self.make_enroll(service)
        service.apply(action, self.approvals(action), self.policy)

        lease = self.storage.acquire_wallet_governance_outbox_lease(self.principal)
        self.assertIsNotNone(lease)
        dispatcher = self.make_dispatcher()
        busy = dispatcher.dispatch_pending(self.principal)
        self.assertEqual(busy[0]["status"], "BUSY")
        self.assertFalse(busy[0]["delivered"])

        self.storage.release_wallet_governance_outbox_lease(self.principal, lease)
        completed = dispatcher.dispatch_pending(self.principal)
        self.assertEqual(len(completed), 1)
        self.assertTrue(completed[0]["delivered"])

    def test_expired_dispatcher_lease_can_be_reclaimed(self):
        first = self.storage.acquire_wallet_governance_outbox_lease(
            self.principal,
            lease_seconds=1,
        )
        self.assertIsNotNone(first)
        # Move the lease expiry into the past without sleeping.
        with self.storage._lock:
            self.storage._conn.execute(
                "UPDATE wallet_governance_outbox_leases SET lease_expires_at = ? "
                "WHERE installation_principal = ?",
                (time.time() - 1, self.principal),
            )
            self.storage._conn.commit()
        second = self.storage.acquire_wallet_governance_outbox_lease(self.principal)
        self.assertIsNotNone(second)
        self.assertNotEqual(first, second)
        self.storage.release_wallet_governance_outbox_lease(self.principal, second)

    def test_bad_remote_checkpoint_is_not_acknowledged(self):
        class TamperedTransport:
            def __init__(self, log):
                self.log = log

            def append_envelope(self, installation_principal, envelope):
                bundle = self.log.append_envelope(installation_principal, envelope)
                bundle["checkpoint"]["payload"]["log_id"] = "forged-log"
                return bundle

        dispatcher = self.make_dispatcher(TamperedTransport(self.external_log))
        service = WalletEnrollmentService(
            self.storage,
            transparency_dispatcher=dispatcher,
        )
        action = self.make_enroll(service)
        result = service.apply(action, self.approvals(action), self.policy)

        self.assertEqual(result["status"], "PENDING_TRANSPARENCY")
        event = self.storage.wallet_governance_outbox_event(action["action_id"])
        self.assertEqual(event["status"], "PENDING")
        self.assertIn("checkpoint", event["last_error"].lower())


if __name__ == "__main__":
    unittest.main()
