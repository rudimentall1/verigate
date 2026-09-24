import base64
import hashlib
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from core.authority import (
    validate_delegation_scope,
    AuthorityGraph,
    CapabilityDelegationService,
    sign_delegation,
)
from core.capabilities import CapabilityRegistry
from core.identity import IdentityRegistry
from core.models import AgentIdentity, Capability
from core.storage import Storage


def identity_for(agent_id: str, private_key: Ed25519PrivateKey):
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    identity_id = hashlib.sha256(raw).hexdigest()
    return AgentIdentity(
        agent_id=agent_id,
        public_key_b64=base64.b64encode(raw).decode("ascii"),
        key_id=identity_id,
    )


class AuthorityGraphTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(Path(self.tmp.name) / "authority.db")
        self.identities = IdentityRegistry(self.storage)
        self.delegator_key = Ed25519PrivateKey.generate()
        self.recipient_key = Ed25519PrivateKey.generate()
        self.delegator = identity_for("agent-root", self.delegator_key)
        self.recipient = identity_for("agent-child", self.recipient_key)
        self.identities.register(self.delegator)
        self.identities.register(self.recipient)

        self.root = Capability(
            capability_id="cap-root",
            agent_id=self.delegator.agent_id,
            identity_id=self.delegator.key_id,
            allowed_actions=("payment", "api.call"),
            allowed_targets=("merchant-a", "merchant-b"),
            allowed_networks=("base", "ethereum"),
            allowed_assets=("USDC",),
            max_per_action={"USDC": 100.0},
            aggregate_limits={"daily_usd": 1000.0},
            conditions=("simulation_required",),
            delegation_depth=0,
        )
        CapabilityRegistry(self.storage).register(self.root)
    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def child_capability(self):
        return Capability(
            capability_id="cap-child",
            agent_id=self.recipient.agent_id,
            identity_id=self.recipient.key_id,
            delegated_from=self.root.capability_id,
            delegated_by_identity_id=self.delegator.key_id,
            delegation_depth=1,
            allowed_actions=("payment",),
            allowed_targets=("merchant-a",),
            allowed_networks=("base",),
            allowed_assets=("USDC",),
            max_per_action={"USDC": 50.0},
            aggregate_limits={"daily_usd": 500.0},
            conditions=("simulation_required",),
            expires_at=self.root.expires_at,
        )

    def test_delegation_creates_graph_and_path(self):
        child = self.child_capability()
        signature = sign_delegation(
            self.root.capability_id,
            child,
            self.delegator.key_id,
            self.delegator_key,
        )
        result = CapabilityDelegationService(self.storage).delegate(
            self.root.capability_id,
            child,
            self.delegator.key_id,
            signature,
        )
        self.assertEqual(result["parent_capability_id"], self.root.capability_id)
        self.assertEqual(result["capability"].capability_id, child.capability_id)
        path = result["authority_path"]
        self.assertEqual([item["id"] for item in path], ["cap-root", "cap-child"])

        edges = AuthorityGraph(self.storage).outgoing(
            "capability",
            self.root.capability_id,
        )
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["relation"], "DELEGATES")

    def test_parent_revoke_invalidates_descendant_effective_authority(self):
        child = self.child_capability()
        signature = sign_delegation(
            self.root.capability_id,
            child,
            self.delegator.key_id,
            self.delegator_key,
        )
        CapabilityDelegationService(self.storage).delegate(
            self.root.capability_id,
            child,
            self.delegator.key_id,
            signature,
        )
        self.assertTrue(CapabilityRegistry(self.storage).active(child.capability_id))

        self.assertTrue(self.storage.revoke_capability(self.root.capability_id))
        self.assertFalse(CapabilityRegistry(self.storage).active(child.capability_id))

        with self.assertRaisesRegex(PermissionError, "ineffective authority chain"):
            CapabilityRegistry(self.storage).resolve(child.capability_id)

    def test_delegation_cannot_expand_parent_scope(self):
        child = self.child_capability()
        child = Capability(
            **{
                **child.__dict__,
                "allowed_targets": ("merchant-b",),
                "max_per_action": {"USDC": 150.0},
            }
        )
        signature = sign_delegation(
            self.root.capability_id,
            child,
            self.delegator.key_id,
            self.delegator_key,
        )
        with self.assertRaisesRegex(PermissionError, "exceed.*parent"):
            CapabilityDelegationService(self.storage).delegate(
                self.root.capability_id,
                child,
                self.delegator.key_id,
                signature,
            )
    def test_invalid_delegation_signature_is_rejected(self):
        child = self.child_capability()
        bad_signature = sign_delegation(
            self.root.capability_id,
            child,
            self.delegator.key_id,
            self.recipient_key,
        )
        with self.assertRaisesRegex(PermissionError, "invalid or tampered"):
            CapabilityDelegationService(self.storage).delegate(
                self.root.capability_id,
                child,
                self.delegator.key_id,
                bad_signature,
            )

    def test_delegation_cannot_survive_revoked_delegator_identity(self):
        child = self.child_capability()
        signature = sign_delegation(
            self.root.capability_id,
            child,
            self.delegator.key_id,
            self.delegator_key,
        )
        CapabilityDelegationService(self.storage).delegate(
            self.root.capability_id,
            child,
            self.delegator.key_id,
            signature,
        )
        self.assertTrue(self.storage.revoke_identity(self.delegator.key_id))
        self.assertFalse(CapabilityRegistry(self.storage).active(self.root.capability_id))
        self.assertFalse(CapabilityRegistry(self.storage).active(child.capability_id))


if __name__ == "__main__":
    unittest.main()


class TestDelegationConstraintNarrowing(unittest.TestCase):
    def test_purpose_and_context_must_narrow(self):
        parent = Capability(capability_id="parent", agent_id="a", identity_id="id", allowed_purposes=("pay", "refund"), context_constraints={"region": ("EU", "UK"), "channel": "mcp"})
        narrowed = Capability(capability_id="child", agent_id="b", identity_id="child-id", delegated_from="parent", delegated_by_identity_id="id", delegation_depth=1, allowed_purposes=("pay",), context_constraints={"region": ("EU",), "channel": "mcp"})
        widened = Capability(capability_id="child2", agent_id="b", identity_id="child-id", delegated_from="parent", delegated_by_identity_id="id", delegation_depth=1, allowed_purposes=("pay", "refund", "charge"), context_constraints={"region": ("EU", "US"), "channel": "mcp"})
        self.assertEqual(validate_delegation_scope(parent, narrowed)[0], True)
        self.assertEqual(validate_delegation_scope(parent, widened)[0], False)
