import base64
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.identity import verify_action_signature
from core.models import ActionIntent
from integrations.agent_sdk import (
    build_arc_enrollment_package,
    build_arc_payment_authorization_request,
    load_or_create_agent_key,
    public_identity,
)

SENDER = "0x1111111111111111111111111111111111111111"
RECIPIENT = "0x2222222222222222222222222222222222222222"


class AgentSdkTest(unittest.TestCase):
    def test_key_is_created_once_and_private_file_is_owner_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys" / "agent.key"
            first = load_or_create_agent_key(path)
            second = load_or_create_agent_key(path)
            encode = lambda key: key.private_bytes(
                serialization.Encoding.Raw,
                serialization.PrivateFormat.Raw,
                serialization.NoEncryption(),
            )
            self.assertEqual(encode(first), encode(second))
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_existing_insecure_key_file_is_rejected(self):
        if os.name != "posix":
            self.skipTest("POSIX file permissions are not available")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "agent.key"
            path.write_bytes(b"x" * 32)
            path.chmod(0o644)
            with self.assertRaises(PermissionError):
                load_or_create_agent_key(path)

    def test_enrollment_package_contains_public_key_only(self):
        key = Ed25519PrivateKey.generate()
        package = build_arc_enrollment_package(
            key,
            agent_id="sdk-agent",
            capability_id="sdk-agent-arc-cap-v1",
            allowed_targets=[RECIPIENT],
            max_per_action_usdc=Decimal("25.00"),
            issued_at=1000,
            expires_at=2000,
        )
        self.assertEqual(package["max_per_action_usdc"], "25.00")
        self.assertEqual(set(package), {
            "schema_version", "agent_id", "public_key_b64", "capability_id",
            "allowed_targets", "max_per_action_usdc", "issued_at", "expires_at",
        })
        self.assertEqual(len(base64.b64decode(package["public_key_b64"])), 32)

    def test_arc_request_signature_verifies_against_registered_public_identity(self):
        key = Ed25519PrivateKey.generate()
        identity = public_identity(key, "sdk-agent")
        request = build_arc_payment_authorization_request(
            key,
            agent_id="sdk-agent",
            identity_id=identity["identity_id"],
            capability_id="sdk-agent-arc-cap-v1",
            sender=SENDER,
            recipient=RECIPIENT,
            amount_usdc="1.250000",
            resource="invoice-123",
            intent_id="sdk-arc-intent-1",
            timestamp=1700000000.0,
        )
        action = ActionIntent(
            agent_id=request["agent_id"],
            action_type=request["action_type"],
            target=request["target"],
            resource=request["resource"],
            amount=Decimal(request["amount_exact"]),
            amount_exact=request["amount_exact"],
            asset=request["asset"],
            network=request["network"],
            intent_id=request["intent_id"],
            timestamp=request["timestamp"],
            metadata=request["metadata"],
        )
        registered_identity = type("Identity", (), {
            "agent_id": identity["agent_id"],
            "public_key_b64": identity["public_key_b64"],
        })()
        valid, reason = verify_action_signature(
            action,
            identity["identity_id"],
            request["agent_signature"],
            registered_identity,
        )
        self.assertTrue(valid, reason)
        self.assertEqual(request["metadata"]["arc"]["chain_id"], 5042)
        self.assertEqual(request["metadata"]["evm_transaction"]["from"], SENDER)
        self.assertEqual(request["metadata"]["evm_transaction"]["data"][-64:], format(1250000, "064x"))


    def test_rejects_identity_id_not_derived_from_signing_key(self):
        key = Ed25519PrivateKey.generate()
        with self.assertRaisesRegex(ValueError, "does not match"):
            build_arc_payment_authorization_request(
                key,
                agent_id="sdk-agent",
                identity_id="0" * 64,
                capability_id="sdk-agent-arc-cap-v1",
                sender=SENDER,
                recipient=RECIPIENT,
                amount_usdc="1",
            )

    def test_enrollment_builder_rejects_invalid_targets_and_non_finite_expiry(self):
        key = Ed25519PrivateKey.generate()
        common = {
            "agent_id": "sdk-agent",
            "capability_id": "sdk-agent-arc-cap-v1",
            "max_per_action_usdc": "25",
            "issued_at": 1000,
            "expires_at": 2000,
        }
        with self.assertRaisesRegex(ValueError, "unique EVM addresses"):
            build_arc_enrollment_package(key, allowed_targets=["*"], **common)
        with self.assertRaisesRegex(ValueError, "finite"):
            build_arc_enrollment_package(
                key, allowed_targets=[RECIPIENT], **{**common, "expires_at": float("inf")}
            )


if __name__ == "__main__":
    unittest.main()
