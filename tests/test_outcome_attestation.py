import base64
import copy
import hashlib
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from attest.keys import generate_keypair, load_private_key, load_public_key
from attest.receipt import sign_execution_receipt
from core.engine import GuardrailEngine
from core.effect_verification import digest
from core.models import ActionIntent, AgentIdentity, Capability
from core.outcome import (
    OutcomeAttestationService,
    build_outcome_attestation,
    build_outcome_claim,
)
from core.policy import Policy
from core.identity import sign_action_intent
from core.storage import Storage
from enforcement.router import ExecutionRouter
from enforcement.networks import NetworkRegistry
from enforcement.chain_verification import EVMChainVerifier
from enforcement.evm_rpc import EvmRpcClient
from enforcement.tool import ToolExecutionAdapter


class OutcomeAttestationTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.private_path = root / "issuer.key"
        self.public_path = root / "issuer.pub"
        self.db_path = root / "outcome.db"
        generate_keypair(self.private_path, self.public_path)
        self.private_key = load_private_key(self.private_path)
        self.public_key = load_public_key(self.public_path)
        self.storage = Storage(self.db_path)

    def tearDown(self):
        self.storage.close()
        self.tmpdir.cleanup()

    def _confirmed_execution(self):
        agent_key = Ed25519PrivateKey.generate()
        raw = agent_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        identity_id = hashlib.sha256(raw).hexdigest()
        identity = AgentIdentity(
            agent_id="outcome-agent",
            public_key_b64=base64.b64encode(raw).decode("ascii"),
            key_id=identity_id,
        )
        self.storage.register_identity(identity)
        capability = Capability(
            capability_id="cap-outcome",
            agent_id=identity.agent_id,
            identity_id=identity_id,
            allowed_actions=("mcp.tool.call",),
            allowed_targets=("github.create_issue",),
        )
        self.storage.register_capability(capability)

        policy_path = Path(self.tmpdir.name) / "policy.yaml"
        policy_path.write_text(
            "allowed_action_types: [mcp.tool.call]\n"
            "allowed_targets: [github.create_issue]\n",
            encoding="utf-8",
        )
        engine = GuardrailEngine(
            Policy.load(policy_path),
            self.storage,
            policy_source_ref=str(policy_path),
        )
        action = ActionIntent(
            agent_id=identity.agent_id,
            action_type="mcp.tool.call",
            target="github.create_issue",
            metadata={"arguments": {"title": "outcome"}},
        )
        signature = sign_action_intent(action, identity_id, agent_key)
        artifacts = engine.authorize_action(
            action,
            capability.capability_id,
            identity_id,
            signature,
            self.private_key,
        )
        authorization = artifacts["execution_authorization"]

        adapter = ToolExecutionAdapter(
            self.storage,
            self.public_key,
            {"github.create_issue": lambda _action: "ready"},
        )
        router = ExecutionRouter(
            NetworkRegistry(),
            self.storage,
            self.public_key,
            self.private_key,
            generic_adapters={"mcp.tool.call": adapter},
        )
        submitted = router.execute_with_receipt(
            authorization,
            lambda _action: {"transaction_hash": "outcome-effect"},
            executor="executor-1",
        )
        confirmed = router.confirm_execution_receipt(
            submitted.as_dict(),
            {
                "state": "CONFIRMED",
                "transaction_ref": "outcome-effect",
                "block_ref": "external-check",
            },
            executor="executor-1",
        )
        return authorization, confirmed


    def _submitted_evm_execution(self):
        agent_key = Ed25519PrivateKey.generate()
        raw = agent_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        identity_id = hashlib.sha256(raw).hexdigest()
        agent_id = "outcome-evm-agent"
        identity = AgentIdentity(
            agent_id=agent_id,
            public_key_b64=base64.b64encode(raw).decode("ascii"),
            key_id=identity_id,
        )
        self.storage.register_identity(identity)

        token = "0x" + "c" * 40
        sender = "0x" + "a" * 40
        recipient = "0x" + "b" * 40
        amount = 10_000_000
        calldata = (
            "0xa9059cbb"
            + recipient[2:].rjust(64, "0")
            + format(amount, "064x")
        )
        transaction_hash = "0x" + "1" * 64
        block_hash = "0x" + "d" * 64

        capability = Capability(
            capability_id="cap-outcome-evm",
            agent_id=agent_id,
            identity_id=identity_id,
            allowed_actions=("payment",),
            allowed_targets=(recipient,),
            allowed_networks=("base",),
            allowed_assets=("USDC",),
        )
        self.storage.register_capability(capability)
        policy_path = Path(self.tmpdir.name) / "evm-policy.yaml"
        policy_path.write_text(
            "allowed_action_types: [payment]\n"
            f'allowed_targets: ["{recipient}"]\n',
            encoding="utf-8",
        )
        policy = Policy.load(policy_path)
        engine = GuardrailEngine(
            policy,
            self.storage,
            policy_source_ref=str(policy_path),
        )
        action = ActionIntent(
            agent_id=agent_id,
            action_type="payment",
            target=recipient,
            asset="USDC",
            network="base",
            amount=Decimal("10"),
            metadata={
                "evm_transaction": {
                    "chain_id": 8453,
                    "to": token,
                    "value_wei": 0,
                    "data": calldata,
                }
            },
        )
        signature = sign_action_intent(action, identity_id, agent_key)
        artifacts = engine.authorize_action(
            action,
            capability.capability_id,
            identity_id,
            signature,
            self.private_key,
        )
        authorization = artifacts["execution_authorization"]

        router = ExecutionRouter(
            NetworkRegistry(),
            self.storage,
            self.public_key,
            self.private_key,
        )
        submitted = router.execute_with_receipt(
            authorization,
            lambda _tx: {"transaction_hash": transaction_hash},
            executor="anna-eip1193-wallet",
        )
        submission_data = {
            "source": "anna_eip1193_wallet",
            "sender": sender,
            "chain_id": 8453,
            "to": token,
            "value_wei": 0,
            "calldata_sha256": hashlib.sha256(calldata.lower().encode("utf-8")).hexdigest(),
        }
        receipt = sign_execution_receipt(
            authorization,
            status="SUBMITTED",
            transaction_ref=transaction_hash,
            executor="anna-eip1193-wallet",
            private_key=self.private_key,
            receipt_id=submitted.payload["receipt_id"],
            submission_data=submission_data,
        )
        self.storage.update_execution_receipt(receipt.as_dict())

        transfer_topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
        sender_topic = "0x" + sender[2:].rjust(64, "0")
        recipient_topic = "0x" + recipient[2:].rjust(64, "0")
        amount_word = "0x" + format(amount, "064x")
        transfer_log = {
            "address": token,
            "topics": [transfer_topic, sender_topic, recipient_topic],
            "data": amount_word,
        }

        def transport(_endpoint, payload, _headers, _timeout):
            request = json.loads(payload)
            method = request["method"]
            if method == "eth_chainId":
                result = {"result": "0x2105"}
            elif method == "eth_getTransactionByHash":
                result = {"result": {
                    "hash": transaction_hash,
                    "from": sender,
                    "to": token,
                    "input": calldata,
                    "value": "0x0",
                    "chainId": "0x2105",
                    "blockNumber": "0x10",
                    "blockHash": block_hash,
                }}
            elif method == "eth_getTransactionReceipt":
                result = {"result": {
                    "transactionHash": transaction_hash,
                    "status": "0x1",
                    "blockNumber": "0x10",
                    "blockHash": block_hash,
                    "from": sender,
                    "to": token,
                    "logs": [transfer_log],
                }}
            elif method == "eth_getBlockByNumber":
                result = {"result": {
                    "number": request["params"][0],
                    "hash": block_hash,
                }}
            elif method == "eth_blockNumber":
                result = {"result": "0x1b"}
            else:
                raise AssertionError(method)
            return json.dumps(result).encode("utf-8")

        observed = EVMChainVerifier(
            expected_sender=sender,
            min_confirmations=12,
        ).verify_receipt(
            authorization,
            EvmRpcClient("http://rpc.test", transport=transport),
            transaction_hash=transaction_hash,
            observed_at=100.0,
        )
        return authorization, receipt, observed, {
            "sender": sender,
            "token": token,
            "recipient": recipient,
            "calldata": calldata,
            "transaction_hash": transaction_hash,
        }

    def _chain_attestation(self, receipt, observed_effect=None, *, status="SUCCEEDED", attestor_id="chain-verifier-test"):
        service = OutcomeAttestationService(self.storage, self.public_key)
        key = self._register(service, attestor_id, "CHAIN_VERIFIER")
        claim = build_outcome_claim(
            receipt.as_dict(),
            status=status,
            executor_id="anna-eip1193-wallet",
            evidence_kind="CHAIN_RECEIPT",
            evidence_ref=(
                observed_effect["evidence_ref"]
                if isinstance(observed_effect, dict)
                else "evm:test/" + receipt.payload["transaction_ref"]
            ),
            result_sha256=(
                observed_effect["result_sha256"]
                if isinstance(observed_effect, dict)
                else hashlib.sha256(b"missing-observation").hexdigest()
            ),
            observed_effect=observed_effect,
        )
        attestation = build_outcome_attestation(
            claim,
            attestor_id=attestor_id,
            attestor_type="CHAIN_VERIFIER",
            private_key=key,
        )
        return service, attestation

    def _register(self, service, attestor_id, attestor_type):
        key = Ed25519PrivateKey.generate()
        raw = key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        service.register_attestor(
            attestor_id=attestor_id,
            public_key_b64=base64.b64encode(raw).decode("ascii"),
            attestor_type=attestor_type,
        )
        return key


    def test_chain_verifier_can_attest_from_submitted_receipt_with_full_evm_binding(self):
        _authorization, receipt, observed, _fields = self._submitted_evm_execution()
        self.assertEqual(receipt.payload["status"], "SUBMITTED")
        self.assertEqual(observed.effect_status, "SUCCEEDED")
        self.assertEqual(observed.observation["confirmations"], 12)

        service, attestation = self._chain_attestation(
            receipt,
            observed.as_dict(),
            status="SUCCEEDED",
        )
        result = service.verify_and_record(attestation)
        self.assertTrue(result["valid"])
        self.assertIsNotNone(result["authority_event"])
        events = self.storage.authority_events(
            agent_id="outcome-evm-agent",
            capability_id="cap-outcome-evm",
        )
        self.assertEqual(len(events), 1)

    def test_chain_verifier_rejects_claim_without_observed_effect(self):
        _authorization, receipt, _observed, _fields = self._submitted_evm_execution()
        service, attestation = self._chain_attestation(receipt, None)
        with self.assertRaisesRegex(ValueError, "requires a signed ObservedEffect"):
            service.verify_and_record(attestation)
        self.assertEqual(
            self.storage.authority_events(
                agent_id="outcome-evm-agent",
                capability_id="cap-outcome-evm",
            ),
            [],
        )

    def test_chain_verifier_rejects_effect_status_mismatch(self):
        _authorization, receipt, observed, _fields = self._submitted_evm_execution()
        mutated = observed.as_dict()
        mutated["effect_status"] = "FAILED"
        canonical_fields = {
            key: mutated.get(key)
            for key in (
                "verifier_type", "evidence_kind", "effect_status", "authorization_id",
                "action_sha256", "observed_at", "evidence_ref", "result_sha256", "observation",
            )
        }
        mutated["observation_sha256"] = digest(canonical_fields)
        service, attestation = self._chain_attestation(
            receipt,
            mutated,
            status="SUCCEEDED",
        )
        with self.assertRaisesRegex(ValueError, "effect status does not match"):
            service.verify_and_record(attestation)

    def test_chain_verifier_rejects_transaction_hash_and_chain_id_drift(self):
        _authorization, receipt, observed, _fields = self._submitted_evm_execution()

        for field, bad_value, expected_error in (
            ("transaction_hash", "0x" + "2" * 64, "transaction hash does not match"),
            ("chain_id", 1, "chain observation ID does not match"),
        ):
            with self.subTest(field=field):
                mutated = copy.deepcopy(observed.as_dict())
                mutated["observation"][field] = bad_value
                canonical_fields = {
                    key: mutated.get(key)
                    for key in (
                        "verifier_type", "evidence_kind", "effect_status", "authorization_id",
                        "action_sha256", "observed_at", "evidence_ref", "result_sha256", "observation",
                    )
                }
                mutated["observation_sha256"] = digest(canonical_fields)
                service, attestation = self._chain_attestation(
                    receipt,
                    mutated,
                    status="SUCCEEDED",
                    attestor_id="chain-verifier-" + field,
                )
                with self.assertRaisesRegex(ValueError, expected_error):
                    service.verify_and_record(attestation)

    def test_self_report_is_stored_but_does_not_change_authority(self):
        _authorization, receipt = self._confirmed_execution()
        service = OutcomeAttestationService(self.storage, self.public_key)
        key = self._register(service, "executor-1", "EXECUTOR")
        claim = build_outcome_claim(
            receipt.as_dict(),
            status="SUCCEEDED",
            executor_id="executor-1",
            evidence_kind="EXECUTOR_RESULT",
            evidence_ref="executor-report-1",
            result_sha256=hashlib.sha256(b"ready").hexdigest(),
        )
        attestation = build_outcome_attestation(
            claim,
            attestor_id="executor-1",
            attestor_type="EXECUTOR_SELF_REPORT",
            private_key=key,
        )
        result = service.verify_and_record(attestation)
        self.assertTrue(result["valid"])
        self.assertIsNone(result["authority_event"])
        self.assertEqual(self.storage.authority_events(
            agent_id="outcome-agent",
            capability_id="cap-outcome",
        ), [])

    def test_external_attestation_changes_authority_and_is_evidence(self):
        authorization, receipt = self._confirmed_execution()
        service = OutcomeAttestationService(self.storage, self.public_key)
        key = self._register(service, "external-verifier-1", "EXTERNAL_VERIFIER")
        claim = build_outcome_claim(
            receipt.as_dict(),
            status="SUCCEEDED",
            executor_id="executor-1",
            evidence_kind="MCP_RESULT",
            evidence_ref="mcp-verifier-result-1",
            result_sha256=hashlib.sha256(b"verified").hexdigest(),
        )
        attestation = build_outcome_attestation(
            claim,
            attestor_id="external-verifier-1",
            attestor_type="EXTERNAL_VERIFIER",
            private_key=key,
        )
        result = service.verify_and_record(attestation)
        self.assertTrue(result["valid"])
        self.assertIsNotNone(result["authority_event"])
        events = self.storage.authority_events(
            agent_id="outcome-agent",
            capability_id="cap-outcome",
        )
        self.assertEqual(events[-1]["event_type"], "EXECUTION_CONFIRMED")
        self.assertEqual(events[-1]["evidence_ref"], claim["claim_id"])
        self.assertEqual(
            result["claim_sha256"],
            hashlib.sha256(
                __import__("json").dumps(
                    claim,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest(),
        )
        claims = self.storage.outcome_claims_by_authorization(
            authorization["payload"]["authorization_id"]
        )
        self.assertEqual(len(claims), 1)

    def test_tampered_attestation_is_rejected_before_persistence(self):
        _authorization, receipt = self._confirmed_execution()
        service = OutcomeAttestationService(self.storage, self.public_key)
        key = self._register(service, "external-verifier-2", "EXTERNAL_VERIFIER")
        claim = build_outcome_claim(
            receipt.as_dict(),
            status="SUCCEEDED",
            executor_id="executor-1",
            evidence_kind="HTTP_RESPONSE",
            evidence_ref="https://example.test/result/1",
            result_sha256=hashlib.sha256(b"ok").hexdigest(),
        )
        attestation = build_outcome_attestation(
            claim,
            attestor_id="external-verifier-2",
            attestor_type="EXTERNAL_VERIFIER",
            private_key=key,
        )
        attestation["payload"]["claim"]["result_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            service.verify_and_record(attestation)
        self.assertEqual(self.storage.outcome_claims_by_authorization(
            receipt.payload["authorization_id"]
        ), [])
