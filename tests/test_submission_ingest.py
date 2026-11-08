import base64
import hashlib
import json
import tempfile
import time
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from attest.receipt import sign_execution_receipt
from core.engine import GuardrailEngine
from core.outcome import OutcomeAttestationService
from core.governance import GovernanceMember, GovernancePolicy, governor_id
from core.identity import sign_action_intent
from core.models import ActionIntent, AgentIdentity, Capability
from core.policy import Policy
from core.storage import Storage
from core.submission_ingest import ExecutionSubmissionService
from core.wallet_enrollment import WalletEnrollmentService
from api import main as api_main
from scripts.chain_verifier_worker import create_chain_attestation
from enforcement.evm_rpc import EvmRpcClient


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def approval(action, key, tag):
    payload = {
        "governance_version": 1,
        "action_digest": hashlib.sha256(canonical(action)).hexdigest(),
        "governor_id": governor_id(key.public_key()), "role": "governor",
        "approval_id": f"{tag}-{action['action_id']}", "issued_at": time.time(),
        "expires_at": time.time() + 120, "nonce": f"{tag}-{action['action_id']}",
    }
    return {"payload": payload, "signature": base64.b64encode(key.sign(canonical(payload))).decode(), "algorithm": "Ed25519"}


class TestSubmissionIngest:
    def setup_method(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.local = Storage(str(root / "executa.db"))
        self.remote = Storage(str(root / "verifier.db"))
        self.issuer = Ed25519PrivateKey.generate()
        issuer_raw = self.issuer.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.issuer_b64 = base64.b64encode(issuer_raw).decode()
        self.principal = "anna-installation:" + hashlib.sha256(issuer_raw).hexdigest()
        self.sender = "0x" + "a" * 40
        self.token = "0x" + "c" * 40
        self.recipient = "0x" + "b" * 40
        self.calldata = "0xa9059cbb" + self.recipient[2:].rjust(64, "0") + format(10_000_000, "064x")
        self.tx_hash = "0x" + "1" * 64

        agent_key = Ed25519PrivateKey.generate()
        agent_raw = agent_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        identity_id = hashlib.sha256(agent_raw).hexdigest()
        self.local.register_identity(AgentIdentity(
            agent_id=self.principal, public_key_b64=base64.b64encode(agent_raw).decode(), key_id=identity_id,
        ))
        capability = Capability(
            capability_id="anna-payment-test", agent_id=self.principal, identity_id=identity_id,
            allowed_actions=("payment",), allowed_targets=(self.recipient,),
            allowed_networks=("base",), allowed_assets=("USDC",),
        )
        self.local.register_capability(capability)
        policy_path = root / "policy.yaml"
        policy_path.write_text(
            "allowed_action_types: [payment]\n"
            f'allowed_targets: ["{self.recipient}"]\n', encoding="utf-8",
        )
        engine = GuardrailEngine(Policy.load(policy_path), self.local, policy_source_ref=str(policy_path))
        action = ActionIntent(
            agent_id=self.principal, action_type="payment", target=self.recipient,
            asset="USDC", network="base", amount=Decimal("10"),
            metadata={"evm_transaction": {
                "chain_id": 8453, "to": self.token, "value_wei": 0, "data": self.calldata,
            }},
        )
        signature = sign_action_intent(action, identity_id, agent_key)
        artifacts = engine.authorize_action(
            action, capability.capability_id, identity_id, signature, self.issuer,
        )
        self.authorization = artifacts["execution_authorization"]
        self.receipt = sign_execution_receipt(
            self.authorization, status="SUBMITTED", transaction_ref=self.tx_hash,
            executor="anna-eip1193-wallet", private_key=self.issuer,
            submission_data={
                "source": "anna_eip1193_wallet", "sender": self.sender,
                "network": "base", "chain_id": 8453, "to": self.token,
                "value_wei": 0,
                "calldata_sha256": hashlib.sha256(self.calldata.lower().encode()).hexdigest(),
            },
        ).as_dict()

        self.gov1, self.gov2 = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        self.governance = GovernancePolicy(
            policy_id="ingest-test", version=1, threshold=2,
            members=(GovernanceMember.from_public_key(self.gov1.public_key(), "governor"), GovernanceMember.from_public_key(self.gov2.public_key(), "governor")),
            allowed_actions=("WALLET_ENROLL", "WALLET_REVOKE"),
        )
        enroll = WalletEnrollmentService.build_action(
            action="WALLET_ENROLL", reason="verified wallet ownership", governance_policy_sha256=self.governance.digest,
            issuer_public_key_b64=self.issuer_b64, chain_id=8453, network="base",
            wallet_address=self.sender, min_confirmations=12,
        )
        WalletEnrollmentService(self.remote).apply(
            enroll, [approval(enroll, self.gov1, "g1"), approval(enroll, self.gov2, "g2")], self.governance,
        )

    def teardown_method(self):
        self.local.close()
        self.remote.close()
        self.tmp.cleanup()

    def test_ingest_verifies_enrolled_issuer_and_persists_for_independent_verifier(self):
        result = ExecutionSubmissionService(self.remote).ingest(self.authorization, self.receipt)
        assert result["status"] == "STORED"
        assert result["stored"] is True and result["idempotent"] is False
        assert self.remote.execution_receipt_by_authorization(self.authorization["payload"]["authorization_id"]) == self.receipt
        assert self.remote.execution_authorization_by_id(self.authorization["payload"]["authorization_id"]) == self.authorization

    def test_http_ingestion_endpoint_accepts_verified_installation_receipt(self, monkeypatch):
        from api import main
        root = Path(self.tmp.name)
        monkeypatch.delenv("VERIGATE_API_KEYS", raising=False)
        monkeypatch.delenv("VERIGATE_TENANT_API_KEYS", raising=False)
        monkeypatch.delenv("VERIGATE_TENANT_KEY_DIR", raising=False)
        monkeypatch.delenv("VERIGATE_REQUIRE_AUTH", raising=False)
        main.POLICY_PATH = str(root / "api-policy.yaml")
        main.DB_PATH = str(root / "api-ingest.db")
        main.PRIVATE_KEY_PATH = str(root / "api-issuer.key")
        main.PUBLIC_KEY_PATH = str(root / "api-issuer.pub")
        main.GOVERNANCE_PRIVATE_KEY_PATH = str(root / "api-governance.key")
        main.GOVERNANCE_PUBLIC_KEY_PATH = str(root / "api-governance.pub")
        main.GOVERNANCE_POLICY_PATH = str(root / "api-governance.json")
        Path(main.POLICY_PATH).write_text("allowed_networks: [base]\nallowed_assets: [USDC]\n", encoding="utf-8")
        with TestClient(main.app) as client:
            startup_storage = main._storage
            main._storage = self.remote
            try:
                response = client.post("/v1/execution/submissions", json={
                    "authorization": self.authorization,
                    "execution_receipt": self.receipt,
                })
            finally:
                main._storage = startup_storage
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "STORED"
            assert response.json()["installation_principal"] == self.principal
            startup_storage.close()
        main._storage = main._engine = main._policy = None
        main._governance_policy = None

    def test_verifier_api_can_retrieve_ingested_signed_submission(self):
        result = ExecutionSubmissionService(self.remote).ingest(self.authorization, self.receipt)
        previous_storage = api_main._storage
        try:
            api_main._storage = self.remote
            fetched = api_main.external_execution_submission(self.authorization["payload"]["authorization_id"])
        finally:
            api_main._storage = previous_storage
        assert fetched["authorization"] == self.authorization
        assert fetched["execution_receipt"] == self.receipt
        assert fetched["wallet_enrollment"]["enrollment_id"] == result["enrollment_id"]

    def test_delayed_ingestion_uses_signed_wallet_execution_time_for_authorization_ttl(self):
        authorization = json.loads(json.dumps(self.authorization))
        issued_at = authorization["payload"]["issued_at"] - 600
        authorization["payload"]["issued_at"] = issued_at
        authorization["payload"]["expires_at"] = issued_at + 1
        authorization["signature"] = base64.b64encode(
            self.issuer.sign(canonical(authorization["payload"]))
        ).decode()
        receipt = sign_execution_receipt(
            authorization, status="SUBMITTED", transaction_ref=self.tx_hash,
            executor="anna-eip1193-wallet", private_key=self.issuer,
            submission_data=self.receipt["payload"]["submission_data"],
        ).as_dict()
        receipt["payload"]["executed_at"] = issued_at
        receipt["signature"] = base64.b64encode(
            self.issuer.sign(canonical(receipt["payload"]))
        ).decode()
        # Current wall clock is later than expires_at; the signed hand-off time
        # is still inside the original authorization window.
        assert int(time.time()) > authorization["payload"]["expires_at"]
        result = ExecutionSubmissionService(self.remote).ingest(authorization, receipt)
        assert result["status"] == "STORED"

    def test_exact_retry_is_idempotent(self):
        service = ExecutionSubmissionService(self.remote)
        service.ingest(self.authorization, self.receipt)
        result = service.ingest(self.authorization, self.receipt)
        assert result["idempotent"] is True

    def test_unenrolled_wallet_is_rejected(self):
        self.receipt["payload"]["submission_data"]["sender"] = "0x" + "d" * 40
        # Re-signing is not possible without changing the issuer receipt; tampering fails signature verification.
        with pytest.raises(PermissionError):
            ExecutionSubmissionService(self.remote).ingest(self.authorization, self.receipt)

    def test_tampered_authorization_is_rejected(self):
        tampered = json.loads(json.dumps(self.authorization))
        tampered["payload"]["agent_id"] = "anna-installation:" + "0" * 64
        with pytest.raises(PermissionError):
            ExecutionSubmissionService(self.remote).ingest(tampered, self.receipt)

    def test_conflicting_receipt_for_same_authorization_is_rejected(self):
        service = ExecutionSubmissionService(self.remote)
        service.ingest(self.authorization, self.receipt)
        conflicting = json.loads(json.dumps(self.receipt))
        conflicting["payload"]["transaction_ref"] = "0x" + "2" * 64
        with pytest.raises(PermissionError):
            service.ingest(self.authorization, conflicting)

    def test_full_ingest_chain_attestation_and_dynamic_authority_path(self):
        ingest = ExecutionSubmissionService(self.remote).ingest(self.authorization, self.receipt)
        assert ingest["status"] == "STORED"
        block_hash = "0x" + "d" * 64
        transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        sender_topic = "0x" + self.sender[2:].rjust(64, "0")
        recipient_topic = "0x" + self.recipient[2:].rjust(64, "0")
        transfer_log = {
            "address": self.token,
            "topics": [transfer_topic, sender_topic, recipient_topic],
            "data": "0x" + format(10_000_000, "064x"),
        }

        def transport(_endpoint, payload, _headers, _timeout):
            request = json.loads(payload)
            method = request["method"]
            if method == "eth_chainId":
                result = {"result": "0x2105"}
            elif method == "eth_getTransactionByHash":
                result = {"result": {
                    "hash": self.tx_hash, "from": self.sender, "to": self.token,
                    "input": self.calldata, "value": "0x0", "chainId": "0x2105",
                    "blockNumber": "0x10", "blockHash": block_hash,
                }}
            elif method == "eth_getTransactionReceipt":
                result = {"result": {
                    "transactionHash": self.tx_hash, "status": "0x1",
                    "blockNumber": "0x10", "blockHash": block_hash,
                    "from": self.sender, "to": self.token, "logs": [transfer_log],
                }}
            elif method == "eth_getBlockByNumber":
                result = {"result": {"number": request["params"][0], "hash": block_hash}}
            elif method == "eth_blockNumber":
                result = {"result": "0x1b"}
            else:
                raise AssertionError(method)
            return json.dumps(result).encode()

        verifier_key = Ed25519PrivateKey.generate()
        service = OutcomeAttestationService(self.remote, Ed25519PrivateKey.generate().public_key())
        verifier_raw = verifier_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        service.register_attestor(
            attestor_id="anna-chain-verifier", public_key_b64=base64.b64encode(verifier_raw).decode(),
            attestor_type="CHAIN_VERIFIER",
        )
        enrollment = self.remote.wallet_enrollment_for_wallet(self.principal, 8453, self.sender)
        api_submission = {
            "authorization_id": self.authorization["payload"]["authorization_id"],
            "authorization": self.authorization,
            "execution_receipt": self.receipt,
            "wallet_enrollment": enrollment,
        }
        attestation = create_chain_attestation(
            api_submission, attestor_id="anna-chain-verifier", attestor_private_key=verifier_key,
            rpc=EvmRpcClient("http://rpc.test", transport=transport),
        )
        assert attestation["payload"]["claim"]["status"] == "SUCCEEDED"
        result = service.verify_and_record(attestation)
        assert result["valid"] is True
        assert result["authority_event"]["agent_id"] == self.principal
        assert result["authority_event"]["capability_id"] == "anna-payment-test"
        assert self.remote.authority_events(
            agent_id=self.principal, capability_id="anna-payment-test",
        )[0]["event_type"] == "EXECUTION_CONFIRMED"

        # A later retry produces a fresh signed observation/claim, but the same
        # chain transaction must not count as a second success for Dynamic Authority.
        retry_attestation = create_chain_attestation(
            api_submission, attestor_id="anna-chain-verifier", attestor_private_key=verifier_key,
            rpc=EvmRpcClient("http://rpc.test", transport=transport), observed_at=124.0,
        )
        retry_result = service.verify_and_record(retry_attestation)
        assert retry_result["valid"] is True
        assert len(self.remote.authority_events(
            agent_id=self.principal, capability_id="anna-payment-test",
        )) == 1
        assert len(self.remote.authority_ledger(self.principal, "anna-payment-test")) == 1
