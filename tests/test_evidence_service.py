import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from core.evidence import EvidenceGraph
from core.evidence_service import EvidenceGraphService
from core.models import ActionIntent, AgentIdentity, Capability
from core.identity import sign_action_intent
from core.engine import GuardrailEngine
from core.policy import Policy
from core.storage import Storage
from attest.keys import generate_keypair, load_private_key, load_public_key


class EvidenceGraphServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.storage = Storage(root / "evidence.db")
        self.policy_path = root / "policy.yaml"
        self.policy_path.write_text("allowed_action_types: [mcp.tool.call]\nallowed_targets: [github.create_issue]\n", encoding="utf-8")
        self.private_path = root / "issuer.key"
        self.public_path = root / "issuer.pub"
        generate_keypair(self.private_path, self.public_path)
        self.private_key = load_private_key(self.private_path)
        self.public_key = load_public_key(self.public_path)

    def tearDown(self):
        self.storage.close()
        self.tmp.cleanup()

    def _authorization(self):
        agent_key = Ed25519PrivateKey.generate()
        raw = agent_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        identity_id = __import__('hashlib').sha256(raw).hexdigest()
        identity = AgentIdentity(agent_id="snapshot-agent", public_key_b64=__import__('base64').b64encode(raw).decode(), key_id=identity_id)
        capability = Capability(capability_id="cap-snapshot", agent_id=identity.agent_id, identity_id=identity_id, allowed_actions=("mcp.tool.call",), allowed_targets=("github.create_issue",))
        self.storage.register_identity(identity)
        self.storage.register_capability(capability)
        action = ActionIntent(agent_id=identity.agent_id, action_type="mcp.tool.call", target="github.create_issue")
        signature = sign_action_intent(action, identity_id, agent_key)
        engine = GuardrailEngine(Policy.load(self.policy_path), self.storage, policy_source_ref=str(self.policy_path))
        result = engine.authorize_action(action, capability.capability_id, identity_id, signature, self.private_key)
        return result["execution_authorization"]["payload"]["authorization_id"]

    def test_snapshot_is_persistent_and_content_addressed(self):
        authorization_id = self._authorization()
        service = EvidenceGraphService(self.storage, EvidenceGraph(self.storage, self.public_key))
        snapshot = service.snapshot(authorization_id)
        self.assertEqual(snapshot["authorization_id"], authorization_id)
        self.assertEqual(len(snapshot["graph_sha256"]), 64)
        stored = self.storage.evidence_graph_snapshot(snapshot["snapshot_id"])
        self.assertIsNotNone(stored)
        ok, reason = service.verify_snapshot(stored)
        self.assertTrue(ok, reason)

    def test_snapshot_tampering_is_detected(self):
        authorization_id = self._authorization()
        service = EvidenceGraphService(self.storage, EvidenceGraph(self.storage, self.public_key))
        snapshot = service.snapshot(authorization_id)
        tampered = {**snapshot, "graph": {**snapshot["graph"], "agent_id": "attacker"}}
        ok, reason = service.verify_snapshot(tampered)
        self.assertFalse(ok)
        self.assertEqual(reason, "graph digest mismatch")

    def test_multiple_snapshots_preserve_history(self):
        authorization_id = self._authorization()
        service = EvidenceGraphService(self.storage, EvidenceGraph(self.storage, self.public_key))
        first = service.snapshot(authorization_id)
        second = service.snapshot(authorization_id)
        self.assertNotEqual(first["snapshot_id"], second["snapshot_id"])
        history = service.history(authorization_id)
        self.assertEqual(len(history), 2)


if __name__ == "__main__":
    unittest.main()
