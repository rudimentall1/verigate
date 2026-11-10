import base64
import hashlib
import time
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

    def test_arc_authorization_requires_onchain_registry_flow_before_payment(self):
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

        contract = "0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D"
        executor = "0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C"
        registration_hash = "0x" + "a" * 64
        consumption_hash = "0x" + "b" * 64

        def prepare(auth):
            return {
                "contract_address": contract,
                "executor": executor.lower(),
                "authorization_id": "0x" + auth["payload"]["authorization_id"],
                "intent_hash": "0x" + "c" * 64,
                "valid_until": auth["payload"]["expires_at"],
                "registration_transaction": {
                    "chainId": hex(ARC_CHAIN_ID),
                    "from": executor,
                    "to": contract,
                    "data": "0x1234",
                    "value": "0x0",
                },
            }

        def registration(auth, tx_hash):
            return {
                "registered": True,
                "contract_address": contract,
                "executor": executor.lower(),
                "authorization_id": "0x" + auth["payload"]["authorization_id"],
                "intent_hash": "0x" + "c" * 64,
                "transaction_ref": tx_hash,
                "block_ref": "0x100",
                "consume_transaction": {
                    "chainId": hex(ARC_CHAIN_ID),
                    "from": executor,
                    "to": contract,
                    "data": "0x5678",
                    "value": "0x0",
                },
            }

        def consumption(auth, tx_hash):
            return {
                "consumed": True,
                "contract_address": contract,
                "executor": executor.lower(),
                "authorization_id": "0x" + auth["payload"]["authorization_id"],
                "intent_hash": "0x" + "c" * 64,
                "transaction_ref": tx_hash,
                "block_ref": "0x101",
                "block_timestamp": auth["payload"]["issued_at"],
            }

        with (
            patch.object(main.ArcMainnetIntegration, "status", return_value=ARC_STATUS),
            patch.object(main.ArcAuthorityRegistry, "verify_deployment", return_value={"verified": True, "chain_id": ARC_CHAIN_ID}),
            patch.object(main.ArcAuthorityRegistry, "prepare_registration_transaction", side_effect=prepare),
            patch.object(
                main.ArcAuthorityRegistry,
                "registration_verification_time",
                side_effect=lambda auth, tx_hash: auth["payload"]["issued_at"],
            ),
            patch.object(main.ArcAuthorityRegistry, "confirm_registration", side_effect=registration),
            patch.object(main.ArcAuthorityRegistry, "confirm_consumption", side_effect=consumption),
        ):
            with TestClient(main.app) as client:
                main._storage.register_identity(identity)
                main._storage.register_capability(capability)
                response = client.post("/v1/integrations/arc/authorize", json=request)
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                authorization = body["execution_authorization"]
                self.assertIsNotNone(authorization)
                self.assertIsNone(body["wallet_transaction"])
                self.assertEqual(body["arc_authority"]["registration_transaction"]["to"], contract)

                server_public_key = load_pem_public_key(
                    client.get("/v1/public-key").content
                )
                receipt_valid, receipt_reason = verify_receipt(
                    body["decision_receipt"], server_public_key
                )
                self.assertTrue(receipt_valid, receipt_reason)
                valid, reason = verify_execution_authorization(
                    authorization, server_public_key
                )
                self.assertTrue(valid, reason)

                bypass = client.post(
                    "/v1/execution/consume",
                    json={"authorization": authorization},
                )
                self.assertEqual(bypass.status_code, 409)

                registered = client.post(
                    "/v1/integrations/arc/registration/confirm",
                    json={
                        "authorization": authorization,
                        "registration_tx_hash": registration_hash,
                    },
                )
                self.assertEqual(registered.status_code, 200, registered.text)
                self.assertTrue(registered.json()["registered"])
                self.assertEqual(registered.json()["consume_transaction"]["to"], contract)

                consumed = client.post(
                    "/v1/integrations/arc/consume/confirm",
                    json={
                        "authorization": authorization,
                        "registration_tx_hash": registration_hash,
                        "consume_tx_hash": consumption_hash,
                    },
                )
                self.assertEqual(consumed.status_code, 200, consumed.text)
                self.assertTrue(consumed.json()["execute"], consumed.json()["reason"])
                self.assertEqual(consumed.json()["wallet_transaction"]["to"], ARC_USDC_ADDRESS)
                self.assertEqual(consumed.json()["wallet_transaction"]["from"], SENDER)
                self.assertEqual(consumed.json()["wallet_transaction"]["chainId"], hex(ARC_CHAIN_ID))
                self.assertTrue(consumed.json()["arc_authority_evidence"]["consumption"]["transaction_ref"])

                replay = client.post(
                    "/v1/integrations/arc/consume/confirm",
                    json={
                        "authorization": authorization,
                        "registration_tx_hash": registration_hash,
                        "consume_tx_hash": consumption_hash,
                    },
                )
                self.assertFalse(replay.json()["execute"])

    def test_arc_authorization_confirms_after_ttl_when_arc_inclusion_was_before_expiry(self):
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

        contract = "0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D"
        executor = "0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C"
        registration_hash = "0x" + "a" * 64
        consumption_hash = "0x" + "b" * 64

        def prepare(auth):
            return {
                "contract_address": contract,
                "executor": executor.lower(),
                "authorization_id": "0x" + auth["payload"]["authorization_id"],
                "intent_hash": "0x" + "c" * 64,
                "valid_until": auth["payload"]["expires_at"],
                "registration_transaction": {
                    "chainId": hex(ARC_CHAIN_ID),
                    "from": executor,
                    "to": contract,
                    "data": "0x1234",
                    "value": "0x0",
                },
            }

        def registration(auth, tx_hash):
            return {
                "registered": True,
                "contract_address": contract,
                "executor": executor.lower(),
                "authorization_id": "0x" + auth["payload"]["authorization_id"],
                "intent_hash": "0x" + "c" * 64,
                "transaction_ref": tx_hash,
                "block_ref": "0x100",
                "consume_transaction": {
                    "chainId": hex(ARC_CHAIN_ID),
                    "from": executor,
                    "to": contract,
                    "data": "0x5678",
                    "value": "0x0",
                },
            }

        def consumption(auth, tx_hash):
            return {
                "consumed": True,
                "contract_address": contract,
                "executor": executor.lower(),
                "authorization_id": "0x" + auth["payload"]["authorization_id"],
                "intent_hash": "0x" + "c" * 64,
                "transaction_ref": tx_hash,
                "block_ref": "0x101",
                "block_timestamp": auth["payload"]["issued_at"] + 20,
            }

        fixed_issued_at = 1700000000
        with (
            patch.object(main.ArcMainnetIntegration, "status", return_value=ARC_STATUS),
            patch.object(main.ArcAuthorityRegistry, "verify_deployment", return_value={"verified": True, "chain_id": ARC_CHAIN_ID}),
            patch.object(main.ArcAuthorityRegistry, "prepare_registration_transaction", side_effect=prepare),
            patch.object(
                main.ArcAuthorityRegistry,
                "registration_verification_time",
                side_effect=lambda auth, tx_hash: auth["payload"]["issued_at"] + 10,
            ),
            patch.object(main.ArcAuthorityRegistry, "confirm_registration", side_effect=registration),
            patch.object(main.ArcAuthorityRegistry, "confirm_consumption", side_effect=consumption),
        ):
            with TestClient(main.app) as client:
                main._storage.register_identity(identity)
                main._storage.register_capability(capability)
                with patch("core.authorization.time.time", return_value=fixed_issued_at):
                    response = client.post("/v1/integrations/arc/authorize", json=request)
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                authorization = body["execution_authorization"]
                self.assertIsNotNone(authorization)
                self.assertIsNone(body["wallet_transaction"])
                self.assertEqual(body["arc_authority"]["registration_transaction"]["to"], contract)

                server_public_key = load_pem_public_key(
                    client.get("/v1/public-key").content
                )
                receipt_valid, receipt_reason = verify_receipt(
                    body["decision_receipt"], server_public_key
                )
                self.assertTrue(receipt_valid, receipt_reason)
                self.assertEqual(authorization["payload"]["issued_at"], fixed_issued_at)
                self.assertEqual(authorization["payload"]["expires_at"], fixed_issued_at + 300)
                self.assertGreater(int(time.time()), authorization["payload"]["expires_at"])
                valid, reason = verify_execution_authorization(
                    authorization, server_public_key, verification_time=fixed_issued_at + 20
                )
                self.assertTrue(valid, reason)
                expired, _ = verify_execution_authorization(authorization, server_public_key)
                self.assertFalse(expired, "authorization must be expired by real server time")

                bypass = client.post(
                    "/v1/execution/consume",
                    json={"authorization": authorization},
                )
                self.assertEqual(bypass.status_code, 409)

                tampered_authorization = {
                    **authorization,
                    "signature": "A" * 88,
                }

                with patch.object(
                    main.ArcAuthorityRegistry,
                    "registration_verification_time",
                ) as arc_rpc:
                    invalid_registration = client.post(
                        "/v1/integrations/arc/registration/confirm",
                        json={
                            "authorization": tampered_authorization,
                            "registration_tx_hash": registration_hash,
                        },
                    )
                    self.assertEqual(invalid_registration.status_code, 403)
                    arc_rpc.assert_not_called()

                with patch.object(
                    main.ArcAuthorityRegistry,
                    "registration_verification_time",
                ) as arc_rpc:
                    invalid_consumption = client.post(
                        "/v1/integrations/arc/consume/confirm",
                        json={
                            "authorization": tampered_authorization,
                            "registration_tx_hash": registration_hash,
                            "consume_tx_hash": consumption_hash,
                        },
                    )
                    self.assertEqual(invalid_consumption.status_code, 403)
                    arc_rpc.assert_not_called()

                registered = client.post(
                    "/v1/integrations/arc/registration/confirm",
                    json={
                        "authorization": authorization,
                        "registration_tx_hash": registration_hash,
                    },
                )
                self.assertEqual(registered.status_code, 200, registered.text)
                self.assertTrue(registered.json()["registered"])
                self.assertEqual(registered.json()["consume_transaction"]["to"], contract)

                consumed = client.post(
                    "/v1/integrations/arc/consume/confirm",
                    json={
                        "authorization": authorization,
                        "registration_tx_hash": registration_hash,
                        "consume_tx_hash": consumption_hash,
                    },
                )
                self.assertEqual(consumed.status_code, 200, consumed.text)
                self.assertTrue(consumed.json()["execute"], consumed.json()["reason"])
                self.assertEqual(consumed.json()["wallet_transaction"]["to"], ARC_USDC_ADDRESS)
                self.assertEqual(consumed.json()["wallet_transaction"]["from"], SENDER)
                self.assertEqual(consumed.json()["wallet_transaction"]["chainId"], hex(ARC_CHAIN_ID))
                self.assertTrue(consumed.json()["arc_authority_evidence"]["consumption"]["transaction_ref"])

                replay = client.post(
                    "/v1/integrations/arc/consume/confirm",
                    json={
                        "authorization": authorization,
                        "registration_tx_hash": registration_hash,
                        "consume_tx_hash": consumption_hash,
                    },
                )
                self.assertFalse(replay.json()["execute"])

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
