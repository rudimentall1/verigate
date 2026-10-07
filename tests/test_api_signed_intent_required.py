import base64
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from api import main
from core.identity import sign_action_intent
from core.models import AgentIdentity, Capability, PaymentIntent

FLAG = "VERIGATE_REQUIRE_SIGNED_INTENT"


def _setup_paths(root: Path) -> None:
    main.POLICY_PATH = str(root / "policy.yaml")
    main.DB_PATH = str(root / "audit.db")
    main.PRIVATE_KEY_PATH = str(root / "issuer.key")
    main.PUBLIC_KEY_PATH = str(root / "issuer.pub")
    Path(main.POLICY_PATH).write_text(
        "allowed_networks: [base]\nallowed_assets: [USDC]\n", encoding="utf-8"
    )


def _make_identity(agent_id: str):
    key = Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    identity_id = hashlib.sha256(raw).hexdigest()
    identity = AgentIdentity(
        agent_id=agent_id,
        public_key_b64=base64.b64encode(raw).decode("ascii"),
        key_id=identity_id,
    )
    return key, identity_id, identity


def _capability(cap_id: str, agent_id: str, identity_id: str | None):
    return Capability(
        capability_id=cap_id,
        agent_id=agent_id,
        identity_id=identity_id,
        allowed_actions=("payment",),
        allowed_targets=("merchant",),
        allowed_networks=("base",),
        allowed_assets=("USDC",),
    )


def _body(agent_id: str, cap_id: str) -> dict:
    return {
        "agent_id": agent_id,
        "capability_id": cap_id,
        "payee": "merchant",
        "asset": "USDC",
        "network": "base",
        "amount": 1.0,
        "resource": "invoice:1",
    }


class SignedIntentRequiredTest(unittest.TestCase):
    def tearDown(self):
        if main._storage is not None:
            main._storage.close()
        main._storage = None
        main._engine = None
        main._policy = None

    def test_flag_blocks_unsigned_capability_endpoint(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td, mock.patch.dict(os.environ, {FLAG: "1"}):
            _setup_paths(Path(td))
            with TestClient(main.app) as client:
                main._storage.register_capability(_capability("cap-unbound", "agent-x", None))
                r = client.post("/v1/authorize/capability", json=_body("agent-x", "cap-unbound"))
                self.assertEqual(r.status_code, 403)
                self.assertIn("VERIGATE_REQUIRE_SIGNED_INTENT", r.json()["detail"])

    def test_without_flag_unbound_capability_still_works(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(FLAG, None)
            _setup_paths(Path(td))
            with TestClient(main.app) as client:
                main._storage.register_capability(_capability("cap-unbound", "agent-x", None))
                r = client.post("/v1/authorize/capability", json=_body("agent-x", "cap-unbound"))
                self.assertEqual(r.status_code, 200)
                self.assertIsNotNone(r.json()["execution_authorization"])

    def test_flag_still_allows_valid_signed_intent_and_rejects_forged(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td, mock.patch.dict(os.environ, {FLAG: "1"}):
            _setup_paths(Path(td))
            agent_key, identity_id, identity = _make_identity("agent-signed")
            with TestClient(main.app) as client:
                main._storage.register_identity(identity)
                main._storage.register_capability(
                    _capability("cap-signed", identity.agent_id, identity_id)
                )
                intent = PaymentIntent(
                    agent_id=identity.agent_id, payee="merchant", asset="USDC",
                    network="base", amount=1.0, resource="invoice:1",
                    intent_id="intent-signed-001", timestamp=1700000000.0,
                )
                payload = {
                    "identity_id": identity_id,
                    "capability_id": "cap-signed",
                    "agent_id": identity.agent_id,
                    "intent_id": intent.intent_id,
                    "timestamp": intent.timestamp,
                    "payee": intent.payee, "asset": intent.asset,
                    "network": intent.network, "amount": intent.amount,
                    "resource": intent.resource, "metadata": intent.metadata,
                }
                good = sign_action_intent(intent.as_action_intent(), identity_id, agent_key)
                r = client.post("/v1/authorize/identity", json={**payload, "agent_signature": good})
                self.assertEqual(r.status_code, 200)

                other_key = Ed25519PrivateKey.generate()
                forged = sign_action_intent(intent.as_action_intent(), identity_id, other_key)
                intent2 = {**payload, "intent_id": "intent-signed-002", "agent_signature": forged}
                r = client.post("/v1/authorize/identity", json=intent2)
                self.assertEqual(r.status_code, 403)

    def test_identity_bound_capability_rejected_on_unsigned_path_even_without_flag(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(FLAG, None)
            _setup_paths(Path(td))
            _key, identity_id, identity = _make_identity("agent-bound")
            with TestClient(main.app) as client:
                main._storage.register_identity(identity)
                main._storage.register_capability(
                    _capability("cap-bound", identity.agent_id, identity_id)
                )
                r = client.post("/v1/authorize/capability", json=_body("agent-bound", "cap-bound"))
                self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
