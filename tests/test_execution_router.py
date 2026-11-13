import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from attest.keys import generate_keypair, load_private_key, load_public_key
from core.authorization import AuthorizationService
from core.models import ActionIntent, Capability, Decision, GuardrailDecision
from core.storage import Storage
from core.authority_state import DynamicAuthorityService
from core.policy import Policy
from enforcement.evm import EVMExecutionAdapter
from enforcement.networks import NetworkRegistry, UnsupportedNetworkError
from enforcement.router import ExecutionRouter
from enforcement.solana import SolanaExecutionAdapter
from solana_fixtures import make_signed_transfer

DEVNET_GENESIS_HASH = "EtWTRABZaYq6iMfeYKouRu166VU2xqa1wcaWoxPkrZBG"


class ExecutionRouterTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        root = Path(self.tmpdir.name)
        self.private = root / "issuer.key"
        self.public = root / "issuer.pub"
        self.db = root / "audit.db"
        generate_keypair(self.private, self.public)
        self.storage = Storage(self.db)
        self.router = ExecutionRouter(NetworkRegistry(solana_genesis_hash_provider=lambda: DEVNET_GENESIS_HASH), self.storage, load_public_key(self.public))

    def tearDown(self):
        self.storage.close()
        self.tmpdir.cleanup()

    def _authorization(self, intent: ActionIntent, decision: Decision = Decision.ALLOW):
        guardrail = GuardrailDecision(
            intent_id=intent.intent_id,
            agent_id=intent.agent_id,
            decision=decision,
            matched_rules=(),
        )
        if decision != Decision.ALLOW:
            return AuthorizationService().issue(
                intent, guardrail, "router-test-policy", load_private_key(self.private), nonce=intent.intent_id
            )
        capability = Capability(
            capability_id=f"cap-router-{intent.intent_id}",
            agent_id=intent.agent_id,
            allowed_actions=(intent.action_type,),
            allowed_targets=(intent.target,),
            allowed_networks=(intent.network,) if intent.network else (),
            allowed_assets=(intent.asset,) if intent.asset else (),
        )
        self.storage.register_capability(capability)
        authority = DynamicAuthorityService(self.storage).snapshot(
            intent.agent_id, capability.capability_id
        )
        return AuthorizationService().issue(
            intent,
            guardrail,
            Policy().digest,
            load_private_key(self.private),
            nonce=intent.intent_id,
            capability=capability,
            authority=authority,
            policy=Policy(),
        )

    def test_concrete_solana_transaction_cannot_be_overridden_by_generic_adapter(self):
        raw, sender_address, recipient_address = make_signed_transfer()
        intent = ActionIntent(
            agent_id="router-agent", action_type="native.transfer", target=recipient_address,
            amount=0.001, asset="SOL", network="solana",
            metadata={
                "solana_transaction": raw,
                "solana_sender": sender_address,
                "destination": recipient_address,
                "solana_genesis_hash": DEVNET_GENESIS_HASH,
            },
        )
        auth = self._authorization(intent)["execution_authorization"]

        class PermissiveGenericAdapter:
            def validate(self, authorization):
                return True, "accepted"

            def execute(self, authorization, broadcaster):
                raise AssertionError("generic adapter must not receive a concrete Solana transaction")

        generic = PermissiveGenericAdapter()
        router = ExecutionRouter(
            NetworkRegistry(),
            self.storage,
            load_public_key(self.public),
            generic_adapters={"native.transfer": generic},
        )
        sent = []
        with self.assertRaisesRegex(ValueError, "genesis hash provider"):
            router.execute(auth, lambda tx: sent.append(tx) or "unexpected")
        self.assertEqual(sent, [])

    def test_malformed_solana_artifact_cannot_fall_back_to_generic_adapter(self):
        raw, sender_address, recipient_address = make_signed_transfer()
        intent = ActionIntent(
            agent_id="router-agent", action_type="native.transfer", target=recipient_address,
            amount=0.001, asset="SOL", network="solana",
            metadata={
                "solana_transaction": None,
                "solana_sender": sender_address,
                "destination": recipient_address,
                "solana_genesis_hash": DEVNET_GENESIS_HASH,
            },
        )
        auth = self._authorization(intent)["execution_authorization"]

        class PermissiveGenericAdapter:
            def validate(self, authorization):
                return True, "accepted"

        router = ExecutionRouter(
            NetworkRegistry(),
            self.storage,
            load_public_key(self.public),
            generic_adapters={"native.transfer": PermissiveGenericAdapter()},
        )
        with self.assertRaisesRegex(ValueError, "non-empty string"):
            router._adapter(auth)

    def test_ambiguous_evm_and_solana_artifacts_are_rejected(self):
        raw, sender_address, recipient_address = make_signed_transfer()
        intent = ActionIntent(
            agent_id="router-agent", action_type="native.transfer", target=recipient_address,
            amount=0.001, asset="SOL", network="solana",
            metadata={
                "solana_transaction": raw,
                "evm_transaction": {},
                "solana_sender": sender_address,
                "destination": recipient_address,
                "solana_genesis_hash": DEVNET_GENESIS_HASH,
            },
        )
        auth = self._authorization(intent)["execution_authorization"]
        with self.assertRaisesRegex(ValueError, "ambiguous execution transaction"):
            self.router._adapter(auth)


    def test_execute_uses_authorization_snapshot_after_verification(self):
        intent = ActionIntent(
            agent_id="router-agent", action_type="token.transfer", target="merchant",
            asset="USDC", network="base",
            metadata={"evm_transaction": {"chain_id": 8453, "to": "0xMerchant", "value_wei": 0, "data": "0x"}},
        )
        caller_authorization = self._authorization(intent)["execution_authorization"]
        original_verify = self.router._verify_authorization

        def verify_then_mutate(snapshot):
            original_verify(snapshot)
            # Simulate the caller mutating its original object immediately
            # after verification. Router execution must continue from its
            # owned snapshot, not this caller-controlled object.
            caller_authorization["payload"]["action"]["metadata"]["evm_transaction"]["to"] = "0xAttacker"

        sent = []
        with patch.object(self.router, "_verify_authorization", side_effect=verify_then_mutate):
            result = self.router.execute(
                caller_authorization,
                lambda tx: sent.append(tx) or "0xsnapshot",
            )

        self.assertEqual(result, "0xsnapshot")
        self.assertEqual(sent[0]["to"], "0xMerchant")
        self.assertEqual(
            caller_authorization["payload"]["action"]["metadata"]["evm_transaction"]["to"],
            "0xAttacker",
        )

    def test_routes_base_to_evm_adapter(self):
        intent = ActionIntent(
            agent_id="router-agent", action_type="token.transfer", target="merchant",
            asset="USDC", network="base",
            metadata={"evm_transaction": {"chain_id": 8453, "to": "0xMerchant", "value_wei": 0, "data": "0x"}},
        )
        auth = self._authorization(intent)["execution_authorization"]
        self.assertIsInstance(self.router._adapter(auth), EVMExecutionAdapter)
        sent = []
        self.assertEqual(self.router.execute(auth, lambda tx: sent.append(tx) or "0xbase"), "0xbase")
        self.assertEqual(sent[0]["chain_id"], 8453)

    def test_routes_solana_to_solana_adapter(self):
        raw, sender_address, recipient_address = make_signed_transfer()
        intent = ActionIntent(
            agent_id="router-agent", action_type="native.transfer", target=recipient_address,
            amount=0.001, asset="SOL", network="solana",
            metadata={
                "solana_transaction": raw,
                "solana_sender": sender_address,
                "destination": recipient_address,
                "solana_genesis_hash": DEVNET_GENESIS_HASH,
            },
        )
        auth = self._authorization(intent)["execution_authorization"]
        self.assertIsInstance(self.router._adapter(auth), SolanaExecutionAdapter)
        sent = []
        self.assertEqual(self.router.execute(auth, lambda tx: sent.append(tx) or "sol-sig"), "sol-sig")
        self.assertEqual(sent[0]["serialized_transaction"], raw)

    def test_solana_execution_fails_closed_without_live_cluster_provider(self):
        raw, sender_address, recipient_address = make_signed_transfer()
        intent = ActionIntent(
            agent_id="router-agent", action_type="native.transfer", target=recipient_address,
            amount=0.001, asset="SOL", network="solana",
            metadata={
                "solana_transaction": raw,
                "solana_sender": sender_address,
                "destination": recipient_address,
                "solana_genesis_hash": DEVNET_GENESIS_HASH,
            },
        )
        auth = self._authorization(intent)["execution_authorization"]
        router = ExecutionRouter(NetworkRegistry(), self.storage, load_public_key(self.public))
        sent = []
        with self.assertRaisesRegex(ValueError, "genesis hash provider"):
            router.execute(auth, lambda tx: sent.append(tx) or "unexpected")
        self.assertEqual(sent, [])

    def test_solana_execution_fails_closed_on_live_cluster_mismatch(self):
        raw, sender_address, recipient_address = make_signed_transfer()
        intent = ActionIntent(
            agent_id="router-agent", action_type="native.transfer", target=recipient_address,
            amount=0.001, asset="SOL", network="solana",
            metadata={
                "solana_transaction": raw,
                "solana_sender": sender_address,
                "destination": recipient_address,
                "solana_genesis_hash": DEVNET_GENESIS_HASH,
            },
        )
        auth = self._authorization(intent)["execution_authorization"]
        wrong_cluster = "5eykt4UsFv8P8NJdTREpY1d9m5d9rVwYw7zV8Yw7"
        router = ExecutionRouter(
            NetworkRegistry(solana_genesis_hash_provider=lambda: wrong_cluster),
            self.storage,
            load_public_key(self.public),
        )
        sent = []
        with self.assertRaisesRegex(ValueError, "genesis hash mismatch"):
            router.execute(auth, lambda tx: sent.append(tx) or "unexpected")
        self.assertEqual(sent, [])

    def test_solana_cluster_change_before_broadcast_fails_closed(self):
        raw, sender_address, recipient_address = make_signed_transfer()
        intent = ActionIntent(
            agent_id="router-agent", action_type="native.transfer", target=recipient_address,
            amount=0.001, asset="SOL", network="solana",
            metadata={
                "solana_transaction": raw,
                "solana_sender": sender_address,
                "destination": recipient_address,
                "solana_genesis_hash": DEVNET_GENESIS_HASH,
            },
        )
        auth = self._authorization(intent)["execution_authorization"]
        observed = iter([DEVNET_GENESIS_HASH, "changed-genesis"])
        router = ExecutionRouter(
            NetworkRegistry(solana_genesis_hash_provider=lambda: next(observed)),
            self.storage,
            load_public_key(self.public),
        )
        sent = []
        with self.assertRaisesRegex(ValueError, "genesis hash mismatch"):
            router.execute(auth, lambda tx: sent.append(tx) or "unexpected")
        self.assertEqual(sent, [])

    def test_solana_cluster_mismatch_does_not_consume_authorization(self):
        raw, sender_address, recipient_address = make_signed_transfer()
        intent = ActionIntent(
            agent_id="router-agent", action_type="native.transfer", target=recipient_address,
            amount=0.001, asset="SOL", network="solana",
            metadata={
                "solana_transaction": raw,
                "solana_sender": sender_address,
                "destination": recipient_address,
                "solana_genesis_hash": DEVNET_GENESIS_HASH,
            },
        )
        auth = self._authorization(intent)["execution_authorization"]
        wrong_router = ExecutionRouter(
            NetworkRegistry(solana_genesis_hash_provider=lambda: "wrong-genesis"),
            self.storage,
            load_public_key(self.public),
        )
        with self.assertRaisesRegex(ValueError, "genesis hash mismatch"):
            wrong_router.execute(auth, lambda tx: "must-not-broadcast")

        sent = []
        self.assertEqual(
            self.router.execute(auth, lambda tx: sent.append(tx) or "solana-retry-sig"),
            "solana-retry-sig",
        )
        self.assertEqual(len(sent), 1)

    def test_unknown_evm_name_routes_by_signed_chain_id_when_family_is_explicit(self):
        intent = ActionIntent(
            agent_id="router-agent", action_type="token.transfer", target="merchant",
            asset="USDC", network="my-evm",
            metadata={"network_family": "evm", "evm_transaction": {"chain_id": 999999, "to": "0xMerchant", "value_wei": 0, "data": "0x"}},
        )
        auth = self._authorization(intent)["execution_authorization"]
        self.assertIsInstance(self.router._adapter(auth), EVMExecutionAdapter)

    def test_known_network_and_chain_id_mismatch_fails_closed(self):
        intent = ActionIntent(
            agent_id="router-agent", action_type="token.transfer", target="merchant",
            asset="USDC", network="base",
            metadata={"evm_transaction": {"chain_id": 1, "to": "0xMerchant", "value_wei": 0, "data": "0x"}},
        )
        auth = self._authorization(intent)["execution_authorization"]
        ok, reason = self.router.consume(auth)
        self.assertFalse(ok)
        self.assertIn("chain_id mismatch", reason)

    def test_unsupported_network_fails_closed_without_broadcast(self):
        intent = ActionIntent(
            agent_id="router-agent", action_type="token.transfer", target="merchant",
            asset="USDC", network="not-supported",
            metadata={"network_family": "mystery"},
        )
        auth = self._authorization(intent)["execution_authorization"]
        sent = []
        with self.assertRaises(UnsupportedNetworkError):
            self.router.execute(auth, lambda tx: sent.append(tx) or "bad")
        self.assertEqual(sent, [])

    def test_mismatched_confirmation_transaction_is_rejected(self):
        intent = ActionIntent(
            agent_id="router-agent", action_type="token.transfer", target="merchant",
            asset="USDC", network="base",
            metadata={"evm_transaction": {"chain_id": 8453, "to": "0xMerchant", "value_wei": 0, "data": "0x"}},
        )
        auth = self._authorization(intent)["execution_authorization"]
        router = ExecutionRouter(
            NetworkRegistry(), self.storage, load_public_key(self.public), load_private_key(self.private)
        )
        receipt = router.execute_with_receipt(auth, lambda tx: "0xoriginal")
        with self.assertRaises(ValueError):
            router.confirm_execution_receipt(
                receipt.as_dict(),
                {"state": "CONFIRMED", "transaction_ref": "0xattacker"},
            )

    def test_blocked_decision_does_not_create_execution_authorization(self):
        intent = ActionIntent(
            agent_id="router-agent", action_type="token.transfer", target="merchant",
            asset="USDC", network="base",
            metadata={"evm_transaction": {"chain_id": 8453, "to": "0xMerchant", "value_wei": 0, "data": "0x"}},
        )
        artifacts = self._authorization(intent, Decision.BLOCK)
        self.assertIsNone(artifacts["execution_authorization"])


if __name__ == "__main__":
    unittest.main()
