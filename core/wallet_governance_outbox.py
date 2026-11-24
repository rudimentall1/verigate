"""Reliable delivery of wallet governance actions to an independent transparency log."""
from __future__ import annotations

import base64
from typing import Any, Protocol

from core.wallet_governance_transparency import verify_wallet_governance_transparency_bundle
from core.storage import Storage


class WalletGovernanceTransparencyTransport(Protocol):
    """Transport contract for a separately operated transparency-log service."""

    def append_envelope(
        self,
        installation_principal: str,
        envelope: dict[str, Any],
    ) -> dict[str, Any]:
        """Idempotently append one action and return the latest signed log bundle."""
        ...


class WalletGovernanceOutboxDispatcher:
    """Drain a durable local outbox into an independently administered log.

    Delivery is at-least-once. A response can be lost after the remote service
    commits; the same action is therefore retried by action_id and the remote
    log's append API MUST be idempotent. A local event is marked DELIVERED only
    after the returned full prefix, checkpoint digest and Ed25519 signature
    have been verified against the independently configured log public key.
    """

    def __init__(
        self,
        storage: Storage,
        transport: WalletGovernanceTransparencyTransport,
        *,
        trusted_log_public_key_b64: str,
    ):
        if not isinstance(trusted_log_public_key_b64, str) or not trusted_log_public_key_b64:
            raise ValueError("independently trusted wallet governance log public key is required")
        try:
            raw_key = base64.b64decode(trusted_log_public_key_b64, validate=True)
        except (TypeError, ValueError):
            raise ValueError("trusted wallet governance log key must be raw Ed25519 base64") from None
        if len(raw_key) != 32:
            raise ValueError("trusted wallet governance log key must contain exactly 32 bytes")
        if not callable(getattr(transport, "append_envelope", None)):
            raise TypeError("wallet transparency transport must provide append_envelope")
        self.storage = storage
        self.transport = transport
        self.trusted_log_public_key_b64 = trusted_log_public_key_b64

    def dispatch_pending(
        self,
        installation_principal: str | None = None,
        *,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Deliver pending actions in local acceptance order under a per-principal lease."""
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("outbox dispatch limit must be a positive integer")

        if installation_principal is None:
            pending = self.storage.wallet_governance_outbox_events()
            principals = list(dict.fromkeys(
                item["installation_principal"]
                for item in pending if item["status"] == "PENDING"
            ))
            results: list[dict[str, Any]] = []
            remaining = limit
            for principal in principals:
                current = self._dispatch_principal(principal, limit=remaining)
                results.extend(current)
                remaining -= sum(1 for item in current if item.get("delivered"))
                if remaining <= 0:
                    break
            return results

        return self._dispatch_principal(installation_principal, limit=limit)

    def _dispatch_principal(
        self,
        installation_principal: str,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        events = self.storage.wallet_governance_outbox_events(installation_principal)
        pending_events = [item for item in events if item["status"] == "PENDING"]
        if not pending_events:
            return []

        lease_token = self.storage.acquire_wallet_governance_outbox_lease(
            installation_principal,
        )
        if lease_token is None:
            return [{
                "action_id": pending_events[0]["action_id"],
                "installation_principal": installation_principal,
                "status": "BUSY",
                "delivered": False,
                "reason": "another transparency outbox worker holds the installation lease",
            }]

        try:
            # Reload under the lease so another process cannot change the local
            # acceptance prefix while this worker is delivering it.
            events = self.storage.wallet_governance_outbox_events(installation_principal)
            results: list[dict[str, Any]] = []
            delivered_this_call = 0
            for index, event in enumerate(events):
                if event["status"] == "DELIVERED":
                    continue
                if delivered_this_call >= limit:
                    break

                action_id = event["action_id"]
                prefix = events[: index + 1]
                expected_envelopes = [item["envelope"] for item in prefix]
                try:
                    bundle = self.transport.append_envelope(
                        installation_principal,
                        event["envelope"],
                    )
                    if not isinstance(bundle, dict):
                        raise ValueError("transparency log returned a malformed bundle")
                    returned_entries = bundle.get("entries")
                    if not isinstance(returned_entries, list):
                        raise ValueError("transparency log returned no append-only entry list")
                    returned_envelopes = []
                    for entry in returned_entries:
                        if not isinstance(entry, dict) or not isinstance(entry.get("payload"), dict):
                            raise ValueError("transparency log returned a malformed entry")
                        returned_envelopes.append(entry["payload"].get("envelope"))

                    if len(returned_envelopes) != len(expected_envelopes) or any(
                        returned != expected
                        for returned, expected in zip(returned_envelopes, expected_envelopes)
                    ):
                        raise ValueError(
                            "transparency log response is not the exact locally accepted outbox prefix"
                        )

                    checkpoint = bundle.get("checkpoint")
                    checkpoint_digest = (
                        checkpoint.get("checkpoint_sha256")
                        if isinstance(checkpoint, dict) else None
                    )
                    if not isinstance(checkpoint_digest, str):
                        raise ValueError("transparency log response is missing its checkpoint digest")

                    valid, reason, _checks = verify_wallet_governance_transparency_bundle(
                        bundle,
                        history_envelopes=expected_envelopes,
                        installation_principal=installation_principal,
                        trusted_log_public_key_b64=self.trusted_log_public_key_b64,
                        trusted_checkpoint_sha256=checkpoint_digest,
                    )
                    if not valid:
                        raise ValueError(reason)

                    self.storage.mark_wallet_governance_outbox_delivered(
                        action_id,
                        bundle,
                    )
                    results.append({
                        "action_id": action_id,
                        "installation_principal": installation_principal,
                        "status": "DELIVERED",
                        "delivered": True,
                        "checkpoint_sha256": checkpoint_digest,
                    })
                    delivered_this_call += 1
                except Exception as exc:
                    self.storage.mark_wallet_governance_outbox_failed(action_id, str(exc))
                    results.append({
                        "action_id": action_id,
                        "installation_principal": installation_principal,
                        "status": "PENDING",
                        "delivered": False,
                        "reason": str(exc),
                    })
                    # Preserve append order: do not send a later event while an
                    # earlier accepted action remains unacknowledged.
                    break
            return results
        finally:
            self.storage.release_wallet_governance_outbox_lease(
                installation_principal,
                lease_token,
            )
