"""Local execution gate for one-time execution authorizations.

The gate is the execution-side boundary: cryptographic verification is
followed by persistent, atomic nonce consumption before a side effect.
"""
from __future__ import annotations

import time
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from attest.receipt import verify_execution_authorization
from core.storage import Storage
from enforcement.protocol import ExecutionAdapter


class ExecutionGate(ExecutionAdapter):
    """Fail-closed local gate for short-lived execution capabilities."""

    def __init__(self, storage: Storage, public_key: Ed25519PublicKey):
        self.storage = storage
        self.public_key = public_key

    def consume(self, authorization: dict[str, Any]) -> tuple[bool, str]:
        """Verify and consume an authorization exactly once.

        This method does not perform the side effect itself. Callers must only
        execute after it returns (True, ...). Nonce consumption is persistent
        and protected by a UNIQUE database constraint.
        """
        ok, reason = verify_execution_authorization(
            authorization,
            self.public_key,
        )
        if not ok:
            return False, reason

        payload = authorization["payload"]
        if int(payload["issued_at"]) > int(time.time()):
            return False, "execution authorization is not active yet"

        consumed = self.storage.consume_execution_nonce(
            nonce=payload["nonce"],
            authorization_id=payload["authorization_id"],
            intent_id=payload["intent_id"],
            agent_id=payload["agent_id"],
        )
        if not consumed:
            return False, "execution authorization already consumed"

        return True, "execution authorization consumed"

    def execute(
        self,
        authorization: dict[str, Any],
        side_effect: Callable[[], Any],
    ) -> Any:
        """Consume the capability, then invoke exactly one side effect.

        The callback is unreachable unless authorization verification and
        one-time nonce consumption both succeed.
        """
        ok, reason = self.consume(authorization)
        if not ok:
            raise PermissionError(reason)
        return side_effect()
