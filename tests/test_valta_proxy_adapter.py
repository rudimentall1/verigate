from __future__ import annotations

import base64
import hashlib
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from attest.receipt import verify_execution_authorization
from adapters.valta.proxy import (
    ACTION_TYPE,
    PURPOSE,
    VALTA_CHAT_COMPLETIONS_URL,
    ValtaProxyExecutionAdapter,
    action_for_chat_completion,
    canonical_request_bytes,
)
from core.capabilities import CapabilityRegistry
from core.engine import GuardrailEngine
from core.identity import IdentityRegistry, sign_action_intent
from core.models import AgentIdentity, Capability, Decision
from core.policy import Policy
from core.storage import Storage
from enforcement.networks import NetworkRegistry
from enforcement.router import ExecutionRouter


class FakeValtaClient:
    def __init__(self):
        self.calls = []

    def chat_completions(self, request_body: bytes, run_id: str) -> dict:
        self.calls.append((request_body, run_id))
        return {
            "id": "chatcmpl-valta-mock",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "mock response"}, "finish_reason": "stop"}],
        }


class ValtaProxyAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.storage = Storage(Path(self.tempdir.name) / "verigate.db")
        self.addCleanup(self.storage.close)

        self.issuer_private_key = Ed25519PrivateKey.generate()
        self.issuer_public_key = self.issuer_private_key.public_key()

        self.agent_id = "valta-pilot-agent"
        self.agent_private_key = Ed25519PrivateKey.generate()
        raw_public_key = self.agent_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        identity = AgentIdentity(
            agent_id=self.agent_id,
            public_key_b64=base64.b64encode(raw_public_key).decode("ascii"),
            key_id=hashlib.sha256(raw_public_key).hexdigest(),
        )
        IdentityRegistry(self.storage).register(identity)
        self.identity_id = identity.key_id

        self.capability_id = "cap-valta-proxy-pilot"
        CapabilityRegistry(self.storage).register(
            Capability(
                capability_id=self.capability_id,
                agent_id=self.agent_id,
                identity_id=self.identity_id,
                allowed_actions=(ACTION_TYPE,),
                allowed_purposes=(PURPOSE,),
                allowed_targets=(VALTA_CHAT_COMPLETIONS_URL,),
            )
        )

        policy_raw = {
            "allowed_action_types": [ACTION_TYPE],
            "allowed_purposes": [PURPOSE],
            "allowed_targets": [VALTA_CHAT_COMPLETIONS_URL],
            "allowed_destinations": [VALTA_CHAT_COMPLETIONS_URL],
            "rate_limit_per_minute": 30,
        }
        self.policy = Policy(
            allowed_action_types=policy_raw["allowed_action_types"],
            allowed_purposes=policy_raw["allowed_purposes"],
            allowed_targets=policy_raw["allowed_targets"],
            allowed_destinations=policy_raw["allowed_destinations"],
            rate_limit_per_minute=policy_raw["rate_limit_per_minute"],
            raw=policy_raw,
        )
        self.engine = GuardrailEngine(self.policy, self.storage)
        self.request = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "Valta x Verigate pilot smoke test"}],
            "max_tokens": 32,
            "stream": False,
        }
        self.run_id = "verigate-valta-pilot-001"

    def authorize(self, request=None, *, engine=None):
        request = self.request if request is None else request
        engine = self.engine if engine is None else engine
        action = action_for_chat_completion(
            agent_id=self.agent_id,
            run_id=self.run_id,
            request=request,
        )
        signature = sign_action_intent(action, self.identity_id, self.agent_private_key)
        return engine.authorize_action(
            action,
            self.capability_id,
            self.identity_id,
            signature,
            self.issuer_private_key,
        )

    def router(self, adapter):
        return ExecutionRouter(
            NetworkRegistry(),
            self.storage,
            self.issuer_public_key,
            generic_adapters={ACTION_TYPE: adapter},
        )

    def test_allow_consumes_authorization_before_valta_request(self):
        artifacts = self.authorize()
        self.assertEqual(
            Decision.ALLOW.value,
            artifacts["decision_receipt"]["payload"]["decision"]["decision"],
        )
        authorization = artifacts["execution_authorization"]
        self.assertIsNotNone(authorization)
        self.assertTrue(verify_execution_authorization(authorization, self.issuer_public_key)[0])

        body = canonical_request_bytes(self.request)
        adapter = ValtaProxyExecutionAdapter(body, self.run_id)
        client = FakeValtaClient()
        result = self.router(adapter).execute(
            authorization,
            lambda _authorization: client.chat_completions(body, self.run_id),
        )

        self.assertEqual("chatcmpl-valta-mock", result["id"])
        self.assertEqual(1, len(client.calls))
        self.assertEqual(body, client.calls[0][0])
        self.assertEqual(self.run_id, client.calls[0][1])

    def test_policy_deny_never_mints_execution_authorization(self):
        deny_raw = {
            "allowed_action_types": ["different.action"],
            "allowed_targets": [VALTA_CHAT_COMPLETIONS_URL],
            "allowed_destinations": [VALTA_CHAT_COMPLETIONS_URL],
        }
        deny_policy = Policy(
            allowed_action_types=deny_raw["allowed_action_types"],
            allowed_targets=deny_raw["allowed_targets"],
            allowed_destinations=deny_raw["allowed_destinations"],
            raw=deny_raw,
        )
        deny_engine = GuardrailEngine(deny_policy, self.storage)
        artifacts = self.authorize(engine=deny_engine)

        self.assertEqual(
            Decision.BLOCK.value,
            artifacts["decision_receipt"]["payload"]["decision"]["decision"],
        )
        self.assertIsNone(artifacts["execution_authorization"])

        client = FakeValtaClient()
        self.assertEqual([], client.calls)

    def test_replay_is_rejected_and_valta_is_called_only_once(self):
        artifacts = self.authorize()
        authorization = artifacts["execution_authorization"]
        body = canonical_request_bytes(self.request)
        adapter = ValtaProxyExecutionAdapter(body, self.run_id)
        client = FakeValtaClient()
        router = self.router(adapter)
        send = lambda _authorization: client.chat_completions(body, self.run_id)

        router.execute(authorization, send)
        with self.assertRaisesRegex(PermissionError, "already consumed"):
            router.execute(authorization, send)

        self.assertEqual(1, len(client.calls))

    def test_changed_request_body_is_rejected_before_valta_call(self):
        artifacts = self.authorize()
        authorization = artifacts["execution_authorization"]
        tampered = dict(self.request)
        tampered["max_tokens"] = 4096
        tampered_body = canonical_request_bytes(tampered)
        adapter = ValtaProxyExecutionAdapter(tampered_body, self.run_id)
        client = FakeValtaClient()

        with self.assertRaisesRegex(ValueError, "differs from the signed action"):
            self.router(adapter).execute(
                authorization,
                lambda _authorization: client.chat_completions(tampered_body, self.run_id),
            )

        self.assertEqual([], client.calls)

    def test_streaming_and_invalid_run_ids_are_rejected(self):
        streaming = {**self.request, "stream": True}
        with self.assertRaisesRegex(ValueError, "non-streaming"):
            action_for_chat_completion(
                agent_id=self.agent_id,
                run_id=self.run_id,
                request=streaming,
            )
        with self.assertRaisesRegex(ValueError, "run_id"):
            action_for_chat_completion(
                agent_id=self.agent_id,
                run_id="bad run id",
                request=self.request,
            )


if __name__ == "__main__":
    unittest.main()
