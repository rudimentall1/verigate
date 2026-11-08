"""Governance-controlled enrollment of Anna installation EVM wallets."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
import uuid
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.governance import GovernancePolicy, verify_governance_quorum
from core.outcome import key_fingerprint
from core.storage import Storage
from enforcement.networks import NetworkRegistry, UnsupportedNetworkError

WALLET_ENROLLMENT_ACTIONS = frozenset({"WALLET_ENROLL", "WALLET_REVOKE"})
_EVM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_PRINCIPAL = re.compile(r"^anna-installation:[0-9a-f]{64}$")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _validate_network_chain(network: str, chain_id: int) -> None:
    if not isinstance(network, str) or not network.strip() or network != network.strip().lower():
        raise ValueError("network must be a normalized non-empty name")
    if isinstance(chain_id, bool) or not isinstance(chain_id, int) or chain_id <= 0:
        raise ValueError("chain_id must be a positive integer")
    registry = NetworkRegistry()
    try:
        descriptor = registry.resolve(network)
    except UnsupportedNetworkError:
        # Explicit custom EVM network labels are allowed for private/test chains.
        registry.resolve_evm_chain(chain_id, name=network)
        return
    if descriptor.family != "evm" or descriptor.chain_id != chain_id:
        raise ValueError("network name does not match the supplied EVM chain_id")


def installation_principal(public_key_b64: str) -> tuple[str, str]:
    try:
        raw = base64.b64decode(public_key_b64, validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(raw)
    except (ValueError, TypeError):
        raise ValueError("issuer public key must be a base64-encoded raw Ed25519 key") from None
    if len(raw) != 32:
        raise ValueError("issuer public key must contain exactly 32 bytes")
    return "anna-installation:" + hashlib.sha256(raw).hexdigest(), key_fingerprint(public_key)


class WalletEnrollmentService:
    """Register/revoke EVM wallets under a governed installation principal.

    Wallet ownership is approved by the configured governance quorum. Operators
    must verify wallet control out-of-band before approving WALLET_ENROLL; this
    service does not treat a caller-supplied address as proof of ownership.
    """

    def __init__(self, storage: Storage):
        self.storage = storage

    @staticmethod
    def build_action(
        *, action: str, reason: str, governance_policy_sha256: str,
        issuer_public_key_b64: str | None = None, chain_id: int | None = None,
        network: str | None = None, wallet_address: str | None = None,
        min_confirmations: int | None = None, enrollment_id: str | None = None,
        action_id: str | None = None, nonce: str | None = None,
        issued_at: float | None = None, expires_at: float | None = None,
    ) -> dict[str, Any]:
        if action not in WALLET_ENROLLMENT_ACTIONS:
            raise ValueError("invalid wallet enrollment governance action")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason is required")
        issued = time.time() if issued_at is None else issued_at
        expiry = issued + 300 if expires_at is None else expires_at
        if expiry <= issued:
            raise ValueError("wallet enrollment action expiry is invalid")
        payload: dict[str, Any] = {
            "governance_version": 1, "action_id": action_id or str(uuid.uuid4()),
            "action": action, "reason": reason, "governance_policy_sha256": governance_policy_sha256,
            "issued_at": issued, "expires_at": expiry, "nonce": nonce or str(uuid.uuid4()),
        }
        if action == "WALLET_ENROLL":
            if not issuer_public_key_b64 or not isinstance(chain_id, int) or isinstance(chain_id, bool) or chain_id <= 0:
                raise ValueError("issuer key and positive chain_id are required")
            principal, key_id = installation_principal(issuer_public_key_b64)
            if not isinstance(network, str) or not network.strip():
                raise ValueError("network is required")
            _validate_network_chain(network.strip().lower(), chain_id)
            if not isinstance(wallet_address, str) or not _EVM_ADDRESS.fullmatch(wallet_address):
                raise ValueError("wallet_address must be a valid EVM address")
            if not isinstance(min_confirmations, int) or isinstance(min_confirmations, bool) or min_confirmations < 1:
                raise ValueError("min_confirmations must be a positive integer")
            payload.update({
                "installation_principal": principal, "issuer_key_id": key_id,
                "issuer_public_key_b64": issuer_public_key_b64, "chain_id": chain_id,
                "network": network.strip().lower(), "wallet_address": wallet_address.lower(),
                "min_confirmations": min_confirmations,
                "enrollment_id": enrollment_id or str(uuid.uuid4()),
            })
        else:
            if not isinstance(enrollment_id, str) or not enrollment_id.strip():
                raise ValueError("enrollment_id is required for revocation")
            payload.update({"enrollment_id": enrollment_id})
        return payload

    def evm_verifier_for_wallet(self, installation_principal: str, chain_id: int, wallet_address: str):
        """Construct an EVM verifier only from an active governed enrollment."""
        enrollment = self.storage.wallet_enrollment_for_wallet(
            installation_principal, chain_id, wallet_address,
        )
        if enrollment is None or enrollment["status"] != "ACTIVE":
            raise PermissionError("wallet is not actively enrolled for this installation and chain")
        from enforcement.chain_verification import EVMChainVerifier
        return EVMChainVerifier(
            expected_sender=enrollment["wallet_address"],
            min_confirmations=enrollment["min_confirmations"],
        )

    def apply(self, action: dict[str, Any], approvals: list[dict[str, Any]], policy: GovernancePolicy) -> dict[str, Any]:
        if not isinstance(action, dict):
            raise ValueError("wallet enrollment action must be an object")
        operation = action.get("action")
        if operation not in WALLET_ENROLLMENT_ACTIONS:
            raise PermissionError("unsupported wallet enrollment action")
        if not isinstance(action.get("reason"), str) or not action["reason"].strip():
            raise ValueError("wallet enrollment action reason is required")
        if operation not in policy.allowed_actions:
            raise PermissionError("governance policy does not allow wallet enrollment action")
        ok, reason = verify_governance_quorum(action, approvals, policy)
        if not ok:
            raise PermissionError(reason)
        if action.get("governance_policy_sha256") != policy.digest:
            raise PermissionError("governance policy fingerprint mismatch")

        if operation == "WALLET_ENROLL":
            principal, key_id = installation_principal(action["issuer_public_key_b64"])
            if action.get("installation_principal") != principal or action.get("issuer_key_id") != key_id:
                raise PermissionError("installation principal/key fingerprint mismatch")
            if not _PRINCIPAL.fullmatch(principal):
                raise ValueError("invalid installation principal")
            if not _EVM_ADDRESS.fullmatch(action.get("wallet_address", "")):
                raise ValueError("invalid enrolled EVM wallet address")
            if isinstance(action.get("chain_id"), bool) or not isinstance(action.get("chain_id"), int) or action["chain_id"] <= 0:
                raise ValueError("invalid enrolled EVM chain id")
            _validate_network_chain(action.get("network"), action["chain_id"])
            if not isinstance(action.get("enrollment_id"), str) or not action["enrollment_id"].strip():
                raise ValueError("invalid enrollment id")
            if isinstance(action.get("min_confirmations"), bool) or not isinstance(action.get("min_confirmations"), int) or action["min_confirmations"] < 1:
                raise ValueError("invalid enrolled confirmation threshold")
            enrollment_id = action["enrollment_id"]
            enrollment = {
                "enrollment_id": enrollment_id, "installation_principal": principal,
                "issuer_key_id": key_id, "issuer_public_key_b64": action["issuer_public_key_b64"],
                "chain_id": action["chain_id"], "network": action["network"],
                "wallet_address": action["wallet_address"].lower(),
                "min_confirmations": action["min_confirmations"],
            }
        else:
            enrollment_id = action.get("enrollment_id")
            if not isinstance(enrollment_id, str) or not enrollment_id.strip():
                raise ValueError("invalid enrollment id")
            existing = self.storage.wallet_enrollment(enrollment_id)
            if existing is None:
                raise LookupError("wallet enrollment not found")
            enrollment = None
            principal = existing["installation_principal"]

        envelope = {
            "action": action, "approvals": approvals,
            "governance_policy": policy.as_dict(), "governance_policy_sha256": policy.digest,
            "action_sha256": digest(action), "algorithm": "Ed25519-MULTIPARTY",
            "recorded_at": time.time(),
        }
        saved = self.storage.apply_wallet_enrollment_governance(
            operation=operation, enrollment=enrollment, enrollment_id=enrollment_id,
            installation_principal=principal, envelope=envelope,
        )
        return {"status": "APPLIED", "enrollment": saved, "governance_action": envelope}
