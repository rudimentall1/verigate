import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import main
from integrations.agent_sdk import (
    build_arc_enrollment_package,
    build_arc_payment_authorization_request,
    load_or_create_agent_key,
    public_identity,
)
from integrations.arc import ARC_CHAIN_ID, ARC_USDC_ADDRESS, build_usdc_transfer_calldata
from scripts.enroll_agent_arc import enroll


SENDER = "0x1111111111111111111111111111111111111111"
RECIPIENT = "0x2222222222222222222222222222222222222222"
EXECUTOR = "0x3333333333333333333333333333333333333333"
REGISTRY = "0x4444444444444444444444444444444444444444"
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


class AgentSdkArcApiIntegrationTest(unittest.TestCase):
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

    def test_independent_agent_sdk_completes_arc_authority_api_flow(self):
        now = time.time()
        agent_key = load_or_create_agent_key(Path(self.temp.name) / "agent" / "identity.key")
        identity = public_identity(agent_key, "independent-agent-sdk")
        capability_id = "cap-independent-agent-arc-v1"
        enrollment_package = build_arc_enrollment_package(
            agent_key,
            agent_id=identity["agent_id"],
            capability_id=capability_id,
            allowed_targets=[RECIPIENT],
            max_per_action_usdc="25.00",
            issued_at=now - 1,
            expires_at=now + 3600,
        )

        authorization_request = build_arc_payment_authorization_request(
            agent_key,
            agent_id=identity["agent_id"],
            identity_id=identity["identity_id"],
            capability_id=capability_id,
            sender=SENDER,
            recipient=RECIPIENT,
            amount_usdc="1.250000",
            resource="sdk-integration-test",
            intent_id="independent-agent-arc-sdk-e2e",
            timestamp=now,
        )

        with patch.object(main.ArcMainnetIntegration, "status", return_value=ARC_STATUS), patch.object(
            main.ArcAuthorityRegistry,
            "verify_deployment",
            return_value={"verified": True, "chain_id": ARC_CHAIN_ID},
        ), patch.object(
            main.ArcAuthorityRegistry,
            "prepare_registration_transaction",
            return_value={
                "contract_address": REGISTRY,
                "registration_transaction": {
                    "chainId": "0x13b2", "from": EXECUTOR, "to": REGISTRY,
                    "data": "0x1234", "value": "0x0",
                },
            },
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
                    "chainId": "0x13b2", "from": EXECUTOR, "to": REGISTRY,
                    "data": "0x5678", "value": "0x0",
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
                enrolled_identity_id, enrolled_capability_id = enroll(
                    main._storage, enrollment_package, now=now
                )
                self.assertEqual(enrolled_identity_id, identity["identity_id"])
                self.assertEqual(enrolled_capability_id, capability_id)

                authorized = client.post(
                    "/v1/integrations/arc/authorize",
                    json=authorization_request,
                )
                self.assertEqual(authorized.status_code, 200, authorized.text)
                authorized_body = authorized.json()
                authorization = authorized_body["execution_authorization"]
                self.assertIsNotNone(authorization)
                self.assertEqual(
                    authorization["payload"]["action"]["metadata"]["evm_transaction"]["data"],
                    build_usdc_transfer_calldata(RECIPIENT, "1.250000"),
                )
                self.assertIsNone(authorized_body["wallet_transaction"])

                registration_hash = "0x" + "11" * 32
                registered = client.post(
                    "/v1/integrations/arc/registration/confirm",
                    json={
                        "authorization": authorization,
                        "registration_tx_hash": registration_hash,
                    },
                )
                self.assertEqual(registered.status_code, 200, registered.text)
                self.assertTrue(registered.json()["registered"])

                consume_hash = "0x" + "22" * 32
                consumed = client.post(
                    "/v1/integrations/arc/consume/confirm",
                    json={
                        "authorization": authorization,
                        "registration_tx_hash": registration_hash,
                        "consume_tx_hash": consume_hash,
                    },
                )
                self.assertEqual(consumed.status_code, 200, consumed.text)
                result = consumed.json()
                self.assertTrue(result["execute"], result["reason"])
                self.assertEqual(result["wallet_transaction"]["chainId"], "0x13b2")
                self.assertEqual(result["wallet_transaction"]["from"], SENDER)
                self.assertEqual(result["wallet_transaction"]["to"].lower(), ARC_USDC_ADDRESS.lower())
                self.assertEqual(
                    result["wallet_transaction"]["data"],
                    build_usdc_transfer_calldata(RECIPIENT, "1.250000"),
                )
                self.assertEqual(result["wallet_transaction"]["value"], "0x0")
                self.assertEqual(
                    result["arc_authority_evidence"]["registration"]["transaction_ref"],
                    registration_hash,
                )
                self.assertEqual(
                    result["arc_authority_evidence"]["consumption"]["transaction_ref"],
                    consume_hash,
                )
                router_consume.assert_called_once()
                self.assertEqual(
                    router_consume.call_args.kwargs["verification_time"],
                    authorization["payload"]["issued_at"] + 2,
                )


if __name__ == "__main__":
    unittest.main()
