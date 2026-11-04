from __future__ import annotations

import base64
import hashlib
import os
import tempfile
import time
import uuid
from pathlib import Path
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from adapters.valta import action_for_chat_completion, canonical_request_bytes, ValtaProxyError
from api import main
from core.capabilities import CapabilityRegistry
from core.identity import IdentityRegistry, sign_action_intent
from core.models import AgentIdentity, Capability


class FakeValtaProxyClient:
    def __init__(self):
        self.calls = []

    def chat_completions(self, request_body: bytes, run_id: str) -> dict:
        self.calls.append((request_body, run_id))
        return {"id": "valta-api-mock", "choices": [{"message": {"content": "ok"}}]}


class DeniedValtaProxyClient:
    def chat_completions(self, request_body: bytes, run_id: str) -> dict:
        raise ValtaProxyError(
            "Valta proxy returned HTTP 403",
            status_code=403,
            response={
                "approved": False,
                "reason": "frozen",
                "id": "deny_valta_test",
                "message": "agent is frozen",
            },
        )


class TestValtaApiRoute(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old = {
            name: getattr(main, name)
            for name in (
                "POLICY_PATH", "DB_PATH", "PRIVATE_KEY_PATH", "PUBLIC_KEY_PATH",
                "GOVERNANCE_PRIVATE_KEY_PATH", "GOVERNANCE_PUBLIC_KEY_PATH",
                "GOVERNANCE_POLICY_PATH",
            )
        }
        # Each test gets an isolated Verigate store and issuer keys.
        if main._storage is not None:
            main._storage.close()
        main._storage = main._engine = main._policy = main._governance_policy = None
        main.POLICY_PATH = str(self.root / "policy.yaml")
        main.DB_PATH = str(self.root / "verigate.db")
        main.PRIVATE_KEY_PATH = str(self.root / "issuer.key")
        main.PUBLIC_KEY_PATH = str(self.root / "issuer.pub")
        main.GOVERNANCE_PRIVATE_KEY_PATH = str(self.root / "governance.key")
        main.GOVERNANCE_PUBLIC_KEY_PATH = str(self.root / "governance.pub")
        main.GOVERNANCE_POLICY_PATH = str(self.root / "governance-policy.json")
        self._write_policy()

        self.agent_id = "valta-api-agent"
        self.agent_private_key = Ed25519PrivateKey.generate()
        raw = self.agent_private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.identity = AgentIdentity(
            agent_id=self.agent_id,
            public_key_b64=base64.b64encode(raw).decode("ascii"),
            key_id=hashlib.sha256(raw).hexdigest(),
        )
        self.capability_id = "cap-valta-api"
        self.request = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "route smoke test"}],
            "max_tokens": 16,
            "stream": False,
        }
        self.run_id = "valta-api-test-" + uuid.uuid4().hex[:12]
        self.intent_id = str(uuid.uuid4())
        self.timestamp = time.time()

    def _write_policy(self, *, denied: bool = False):
        policy = (
            "allowed_action_types: [valta.chat_completions]\n"
            "allowed_purposes: [ai_inference]\n"
            'allowed_targets: ["https://valta.co/v1/chat/completions"]\n'
            'allowed_destinations: ["https://valta.co/v1/chat/completions"]\n'
            "rate_limit_per_minute: 30\n"
        )
        if denied:
            policy += 'blocked_destinations: ["https://valta.co/v1/chat/completions"]\n'
        Path(main.POLICY_PATH).write_text(policy, encoding="utf-8")

    def _register_identity_and_capability(self):
        IdentityRegistry(main._storage).register(self.identity)
        CapabilityRegistry(main._storage).register(
            Capability(
                capability_id=self.capability_id,
                agent_id=self.agent_id,
                identity_id=self.identity.key_id,
                allowed_actions=("valta.chat_completions",),
                allowed_purposes=("ai_inference",),
                allowed_targets=("https://valta.co/v1/chat/completions",),
            )
        )

    def _signed_payload(self):
        action = action_for_chat_completion(
            agent_id=self.agent_id,
            run_id=self.run_id,
            request=self.request,
            intent_id=self.intent_id,
            timestamp=self.timestamp,
        )
        signature = sign_action_intent(action, self.identity.key_id, self.agent_private_key)
        return {
            "agent_id": self.agent_id,
            "identity_id": self.identity.key_id,
            "capability_id": self.capability_id,
            "agent_signature": signature,
            "intent_id": self.intent_id,
            "timestamp": self.timestamp,
            "run_id": self.run_id,
            "request": self.request,
        }

    def tearDown(self):
        if main._storage is not None:
            main._storage.close()
        for name, value in self.old.items():
            setattr(main, name, value)
        main._storage = main._engine = main._policy = main._governance_policy = None
        self.tmp.cleanup()

    def test_api_route_executes_only_after_verigate_authorization(self):
        fake = FakeValtaProxyClient()
        with patch.dict(os.environ, {"VALTA_VIRTUAL_KEY": "vk_live_test_only"}):
            with TestClient(main.app) as client:
                self._register_identity_and_capability()
                with patch("api.main.ValtaProxyClient", return_value=fake):
                    response = client.post(
                        "/v1/integrations/valta/chat/completions",
                        json=self._signed_payload(),
                    )

        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] == "executed"
        assert result["decision"] == "ALLOW"
        assert result["execution_authorization"]["signature"]
        assert result["valta_response"]["id"] == "valta-api-mock"
        assert fake.calls == [(canonical_request_bytes(self.request), self.run_id)]

    def test_api_route_rejects_changed_request_before_valta_call(self):
        fake = FakeValtaProxyClient()
        signed = self._signed_payload()
        changed = {**self.request, "max_tokens": 128}
        signed["request"] = changed
        with patch.dict(os.environ, {"VALTA_VIRTUAL_KEY": "vk_live_test_only"}):
            with TestClient(main.app) as client:
                self._register_identity_and_capability()
                with patch("api.main.ValtaProxyClient", return_value=fake):
                    response = client.post(
                        "/v1/integrations/valta/chat/completions",
                        json=signed,
                    )

        assert response.status_code == 403, response.text
        assert fake.calls == []

    def test_api_route_returns_block_without_calling_valta(self):
        fake = FakeValtaProxyClient()
        self._write_policy(denied=True)
        with patch.dict(os.environ, {"VALTA_VIRTUAL_KEY": "vk_live_test_only"}):
            with TestClient(main.app) as client:
                self._register_identity_and_capability()
                with patch("api.main.ValtaProxyClient", return_value=fake):
                    response = client.post(
                        "/v1/integrations/valta/chat/completions",
                        json=self._signed_payload(),
                    )

        assert response.status_code == 403, response.text
        assert response.json()["decision"] == "BLOCK"
        assert fake.calls == []

    def test_api_route_preserves_valta_cap_denial_without_retry(self):
        denied = DeniedValtaProxyClient()
        with patch.dict(os.environ, {"VALTA_VIRTUAL_KEY": "vk_live_test_only"}):
            with TestClient(main.app) as client:
                self._register_identity_and_capability()
                with patch("api.main.ValtaProxyClient", return_value=denied):
                    response = client.post(
                        "/v1/integrations/valta/chat/completions",
                        json=self._signed_payload(),
                    )

        assert response.status_code == 403, response.text
        result = response.json()
        assert result["status"] == "upstream_error"
        assert result["upstream_response"]["reason"] == "frozen"
        assert result["retry_allowed"] is False

    def test_api_route_fails_closed_without_valta_virtual_key(self):
        fake = FakeValtaProxyClient()
        with patch.dict(os.environ, {"VALTA_VIRTUAL_KEY": ""}):
            with TestClient(main.app) as client:
                with patch("api.main.ValtaProxyClient", return_value=fake):
                    response = client.post(
                        "/v1/integrations/valta/chat/completions",
                        json=self._signed_payload(),
                    )

        assert response.status_code == 503, response.text
        assert fake.calls == []
