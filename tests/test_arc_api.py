import base64
import hashlib
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastapi.testclient import TestClient

from api import main
from attest.receipt import verify_execution_authorization, verify_receipt
from core.identity import sign_action_intent
from core.models import ActionIntent, AgentIdentity, Capability
from integrations.arc import (
    ARC_CHAIN_ID,
    ARC_USDC_ADDRESS,
    arc_payment_metadata,
)


SENDER = "0x1111111111111111111111111111111111111111"
RECIPIENT = "0x2222222222222222222222222222222222222222"
ARC_STATUS = {
    "network": "arc",
    "chain_id": ARC_CHAIN_ID,
    "block_number": 123456,
    "native_gas_asset": "USDC",
    "native_gas_decimals": 18,
    "usdc_erc20_address": ARC_USDC_ADDRESS,
    "usdc_erc20_decimals": 6,
    "gas_price_wei": 1,
    "gas_price_native_usdc": "0.000000000000000001",
    "explorer": "https://explorer.arc.io",
    "rpc_host": "rpc.mainnet.arc.io",
    "verified": True,
}


class ArcApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        main.POLICY_PATH = str(root / "policy.yaml")
        main.DB_PATH = str(root / "audit.db")
        main.PRIVATE_KEY_PATH = str(root / "issuer.key")
        main.PUBLIC_KEY_PATH = str(root / "issuer.pub")
        Path(main.POLICY_PATH).write_text(
            "allowed_networks: [arc]\n"
            "allowed_assets: [USDC]\n"
            "per_tx_cap:\n  USDC: 500\n"
            "new_payee_cap:\n  USDC: 50\n"
            "daily_cap:\n  USDC: 2000\n",
            encoding="utf-8",
        )

    def tearDown(self):
        if main._storage is not None:
            main._storage.close()
        main._storage = main._engine = main._policy = None
        self.temp.cleanup()

    def test_arc_status_endpoint_returns_verified_network_metadata(self):
        with patch.object(main.ArcMainnetIntegration, "status", return_value=ARC_STATUS):
            with TestClient(main.app) as client:
                response = client.get("/v1/integrations/arc/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["chain_id"], 5042)
        self.assertEqual(response.json()["usdc_erc20_decimals"], 6)
        self.assertTrue(response.json()["verified"])

    def test_arc_authorization_binds_identity_capability_and_exact_transfer(self):
        agent_key = Ed25519PrivateKey.generate()
        raw_key = agent_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        identity_id = hashlib.sha256(raw_key).hexdigest()
        identity = AgentIdentity(
            agent_id="arc-agent",
            public_key_b64=base64.b64encode(raw_key).decode("ascii"),
            key_id=identity_id,
        )
        capability = Capability(
            capability_id="cap-arc-agent",
            agent_id=identity.agent_id,
            identity_id=identity_id,
            allowed_actions=("payment",),
            allowed_targets=(RECIPIENT,),
            allowed_networks=("arc",),
            allowed_assets=("USDC",),
            max_per_action={"USDC": 50.0},
        )
        metadata = arc_payment_metadata(SENDER, RECIPIENT, "1.25")
        intent = ActionIntent(
            agent_id=identity.agent_id,
            action_type="payment",
            target=RECIPIENT,
            amount=Decimal("1.25"),
            amount_exact="1.25",
            asset="USDC",
            network="arc",
            intent_id="arc-api-intent-001",
            timestamp=1700000000.0,
            metadata=metadata,
        )
        signature = sign_action_intent(intent, identity_id, agent_key)
        request = {
            "identity_id": identity_id,
            "capability_id": capability.capability_id,
            "agent_id": identity.agent_id,
            "agent_signature": signature,
            "intent_id": intent.intent_id,
            "timestamp": intent.timestamp,
            "action_type": intent.action_type,
            "target": intent.target,
            "amount_exact": "1.25",
            "asset": "USDC",
            "network": "arc",
            "metadata": metadata,
        }

        with patch.object(main.ArcMainnetIntegration, "status", return_value=ARC_STATUS), patch.object(
            main.ArcAuthorityRegistry, "verify_deployment", return_value={"verified": True, "chain_id": ARC_CHAIN_ID}
        ), patch.object(
            main.ArcAuthorityRegistry, "prepare_registration_transaction", return_value={
                "contract_address": "0x4444444444444444444444444444444444444444",
                "registration_transaction": {"to": "0x4444444444444444444444444444444444444444", "data": "0x1234"},
            }
        ), patch.object(
            main.ArcAuthorityRegistry,
            "registration_verification_time",
            side_effect=lambda auth, tx_hash: auth["payload"]["issued_at"] + 1,
        ), patch.object(
            main.ArcAuthorityRegistry,
            "confirm_registration",
            side_effect=lambda auth, tx_hash: {
                "registered": True,
                "authorization_id": "0x" + auth["payload"]["authorization_id"],
                "intent_hash": "0x" + "ab" * 32,
                "transaction_ref": tx_hash,
                "block_ref": "0x100",
                "consume_transaction": {
                    "to": "0x4444444444444444444444444444444444444444",
                    "data": "0x5678",
                },
            },
        ), patch.object(
            main.ArcAuthorityRegistry,
            "confirm_consumption",
            side_effect=lambda auth, tx_hash: {
                "consumed": True,
                "authorization_id": "0x" + auth["payload"]["authorization_id"],
                "intent_hash": "0x" + "ab" * 32,
                "transaction_ref": tx_hash,
                "block_ref": "0x101",
                "block_timestamp": auth["payload"]["issued_at"] + 2,
            },
        ), patch.object(
            main.ExecutionRouter, "consume", return_value=(True, "execution authorization consumed")
        ) as router_consume:
            with TestClient(main.app) as client:
                main._storage.register_identity(identity)
                main._storage.register_capability(capability)
                response = client.post("/v1/integrations/arc/authorize", json=request)
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                authorization = body["execution_authorization"]
                self.assertIsNotNone(authorization)
                server_key_response = client.get("/v1/public-key")
                self.assertEqual(server_key_response.status_code, 200)
                server_public_key = load_pem_public_key(server_key_response.content)
                receipt_valid, receipt_reason = verify_receipt(
                    body["decision_receipt"], server_public_key
                )
                self.assertTrue(receipt_valid, f"decision receipt: {receipt_reason}")
                valid, reason = verify_execution_authorization(
                    authorization, server_public_key
                )
                self.assertTrue(valid, reason)
                at_expiry, expiry_reason = verify_execution_authorization(
                    authorization,
                    server_public_key,
                    verification_time=authorization["payload"]["expires_at"],
                )
                self.assertFalse(at_expiry)
                self.assertEqual(expiry_reason, "execution authorization expired")
                self.assertEqual(body["arc_network"]["chain_id"], ARC_CHAIN_ID)
                self.assertEqual(body["arc_authority"]["registration_transaction"]["to"].lower(), body["arc_authority"]["contract_address"].lower())
                self.assertIsNone(body["wallet_transaction"])
                self.assertIn("/v1/integrations/arc/registration/confirm", " ".join(body["execution_order"]))

                # The generic consume route must not bypass the Arc registry.
                consumed = client.post(
                    "/v1/execution/consume",
                    json={"authorization": authorization},
                )
                self.assertEqual(consumed.status_code, 409)
                self.assertIn("on-chain registration", consumed.json()["detail"])

                registration_hash = "0x" + "11" * 32
                consumption_hash = "0x" + "22" * 32
                # Confirmation must use the canonical Arc inclusion timestamp,
                # not wall-clock time at the later HTTP confirmation request.
                # Simulate both confirmations arriving after expiry even though
                # the mocked registration and consumption blocks are pre-expiry.
                with patch(
                    "attest.receipt.time.time",
                    return_value=authorization["payload"]["expires_at"] + 1,
                ):
                    registration = client.post(
                        "/v1/integrations/arc/registration/confirm",
                        json={
                            "authorization": authorization,
                            "registration_tx_hash": registration_hash,
                        },
                    )
                    self.assertEqual(registration.status_code, 200, registration.text)
                    self.assertTrue(registration.json()["registered"])
                    self.assertEqual(
                        registration.json()["consume_transaction"]["to"].lower(),
                        body["arc_authority"]["contract_address"].lower(),
                    )

                    consumption = client.post(
                        "/v1/integrations/arc/consume/confirm",
                        json={
                            "authorization": authorization,
                            "registration_tx_hash": registration_hash,
                            "consume_tx_hash": consumption_hash,
                        },
                    )
                    self.assertEqual(consumption.status_code, 200, consumption.text)
                    result = consumption.json()
                self.assertTrue(result["execute"])
                self.assertEqual(
                    result["arc_authority_evidence"]["registration"]["transaction_ref"],
                    registration_hash,
                )
                self.assertEqual(
                    result["arc_authority_evidence"]["consumption"]["transaction_ref"],
                    consumption_hash,
                )
                self.assertIsNotNone(result["wallet_transaction"])
                router_consume.assert_called_once()
                self.assertEqual(
                    router_consume.call_args.kwargs["verification_time"],
                    authorization["payload"]["issued_at"] + 2,
                )

    def test_arc_endpoint_rejects_non_arc_payment_before_network_or_identity_checks(self):
        request = {
            "identity_id": "identity",
            "capability_id": "capability",
            "agent_id": "agent",
            "agent_signature": "signature",
            "intent_id": "intent",
            "timestamp": 1700000000.0,
            "action_type": "payment",
            "target": RECIPIENT,
            "amount": 1,
            "asset": "USDC",
            "network": "base",
            "metadata": {},
        }
        with TestClient(main.app) as client:
            response = client.post("/v1/integrations/arc/authorize", json=request)
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
