import tempfile
import unittest
from pathlib import Path

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.receipt import verify_execution_authorization, verify_receipt
from core.engine import GuardrailEngine
from core.policy import Policy
from core.policy_version import (
    build_policy_version,
    sign_policy_version,
    verify_policy_version,
)
from core.models import PaymentIntent
from core.storage import Storage


class PolicyVersionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.private = root / "issuer.key"
        self.public = root / "issuer.pub"
        generate_keypair(self.private, self.public)
        self.policy_path = root / "policy.yaml"
        self.policy_path.write_text(
            "allowed_networks: [base]\nallowed_assets: [USDC]\n"
            "per_tx_cap:\n  USDC: 100\n",
            encoding="utf-8",
        )
        self.policy = Policy.load(self.policy_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_policy_version_is_signed_and_verifiable(self):
        version = build_policy_version(
            self.policy,
            source_ref=str(self.policy_path),
            version=7,
            parent_sha256="a" * 64,
        )
        signed = sign_policy_version(
            version,
            load_private_key(self.private),
        ).as_dict()
        ok, reason = verify_policy_version(
            signed,
            load_public_key(self.public),
        )
        self.assertTrue(ok, reason)
        self.assertEqual(signed["payload"]["version"], 7)
        self.assertEqual(
            signed["payload"]["policy_sha256"],
            self.policy.digest,
        )

    def test_tampered_policy_version_is_rejected(self):
        version = build_policy_version(
            self.policy,
            source_ref=str(self.policy_path),
        )
        signed = sign_policy_version(
            version,
            load_private_key(self.private),
        ).as_dict()
        signed["payload"]["version"] = 99
        ok, _ = verify_policy_version(
            signed,
            load_public_key(self.public),
        )
        self.assertFalse(ok)

    def test_engine_binds_policy_version_to_receipt_and_authorization(self):
        storage = Storage(Path(self.tmp.name) / "authority.db")
        try:
            engine = GuardrailEngine(
                self.policy,
                storage,
                policy_source_ref=str(self.policy_path),
                policy_version_number=3,
            )
            intent = PaymentIntent(
                agent_id="agent-policy",
                payee="merchant",
                asset="USDC",
                network="base",
                amount=1.0,
            )
            result = engine.authorize(
                intent,
                load_private_key(self.private),
            )
            receipt = result["decision_receipt"]
            authorization = result["execution_authorization"]
            self.assertIsNotNone(receipt["payload"]["signed_policy_version"])
            self.assertEqual(
                receipt["payload"]["policy_version_sha256"],
                authorization["payload"]["policy_version_sha256"],
            )
            self.assertEqual(
                receipt["payload"]["policy_sha256"],
                receipt["payload"]["signed_policy_version"]["payload"]["policy_sha256"],
            )
            self.assertTrue(
                verify_receipt(
                    receipt,
                    load_public_key(self.public),
                )[0]
            )
            self.assertTrue(
                verify_execution_authorization(
                    authorization,
                    load_public_key(self.public),
                )[0]
            )
            stored = storage.policy_version_by_sha(self.policy.digest)
            self.assertIsNotNone(stored)
            self.assertEqual(stored["payload"]["version"], 3)
        finally:
            storage.close()

    def test_policy_artifact_is_immutable_per_engine(self):
        storage = Storage(Path(self.tmp.name) / "immutable.db")
        try:
            engine = GuardrailEngine(
                self.policy,
                storage,
                policy_source_ref=str(self.policy_path),
                policy_version_number=1,
            )
            first = engine.signed_policy_version(
                load_private_key(self.private)
            )
            second = engine.signed_policy_version(
                load_private_key(self.private)
            )
            self.assertEqual(first, second)
        finally:
            storage.close()


    def test_execution_receipt_preserves_policy_lineage(self):
        from attest.receipt import verify_execution_receipt
        from enforcement.networks import NetworkRegistry
        from enforcement.router import ExecutionRouter

        storage = Storage(Path(self.tmp.name) / "execution-policy.db")
        try:
            engine = GuardrailEngine(
                self.policy,
                storage,
                policy_source_ref=str(self.policy_path),
                policy_version_number=4,
            )
            intent = PaymentIntent(
                agent_id="agent-policy-exec",
                payee="merchant",
                asset="USDC",
                network="base",
                amount=1.0,
            )
            authorization = engine.authorize(
                intent,
                load_private_key(self.private),
            )["execution_authorization"]
            router = ExecutionRouter(
                NetworkRegistry(),
                storage,
                load_public_key(self.public),
                private_key=load_private_key(self.private),
            )
            submitted = router.execute_with_receipt(
                authorization,
                lambda _action: {"tx_hash": "policy-lineage-tx"},
            )
            self.assertEqual(
                submitted.payload["policy_version_sha256"],
                authorization["payload"]["policy_version_sha256"],
            )
            valid, reason = verify_execution_receipt(
                submitted.as_dict(),
                load_public_key(self.public),
                authorization,
            )
            self.assertTrue(valid, reason)
        finally:
            storage.close()



if __name__ == "__main__":
    unittest.main()
