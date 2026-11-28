"""Ingest Anna wallet submission receipts after enrolled-key verification."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from attest.receipt import verify_execution_authorization, verify_execution_receipt
from core.storage import Storage

_EVM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_EVM_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
_HEX_DATA = re.compile(r"^0x(?:[0-9a-fA-F]{2})*$")


class ExecutionSubmissionService:
    """Verify and persist a wallet-submitted receipt for an enrolled installation."""

    def __init__(self, storage: Storage):
        self.storage = storage

    def ingest(self, authorization: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
        try:
            auth_payload = authorization["payload"]
            receipt_payload = receipt["payload"]
            action = auth_payload["action"]
            metadata = action["metadata"]
            expected_tx = metadata["evm_transaction"]
            submission = receipt_payload["submission_data"]
        except (KeyError, TypeError):
            raise ValueError("authorization or wallet receipt is missing required fields") from None

        principal = auth_payload.get("agent_id")
        if not isinstance(principal, str) or not principal.startswith("anna-installation:"):
            raise PermissionError("external wallet submission requires an Anna installation principal")
        if receipt_payload.get("status") != "SUBMITTED":
            raise ValueError("only signed SUBMITTED wallet receipts can be ingested")
        if receipt_payload.get("executor") != "anna-eip1193-wallet" or submission.get("source") != "anna_eip1193_wallet":
            raise PermissionError("submission is not from the Anna EIP-1193 wallet path")

        sender = submission.get("sender")
        chain_id = submission.get("chain_id")
        if (
            not isinstance(sender, str) or not _EVM_ADDRESS.fullmatch(sender)
            or not isinstance(chain_id, int) or isinstance(chain_id, bool) or chain_id <= 0
        ):
            raise ValueError("wallet submission sender or chain_id is malformed")
        enrollment = self.storage.wallet_enrollment_for_wallet(principal, chain_id, sender)
        if enrollment is None or enrollment["status"] != "ACTIVE":
            raise PermissionError("wallet is not actively enrolled for this installation and chain")
        expected_chain_id = expected_tx.get("chain_id")
        expected_to = expected_tx.get("to")
        expected_value = expected_tx.get("value_wei")
        expected_data = expected_tx.get("data")
        if (
            isinstance(expected_chain_id, bool) or not isinstance(expected_chain_id, int)
            or expected_chain_id <= 0 or expected_chain_id != enrollment["chain_id"]
        ):
            raise PermissionError("enrolled chain id does not match signed authorization")
        if not isinstance(expected_to, str) or not _EVM_ADDRESS.fullmatch(expected_to):
            raise ValueError("signed EVM transaction destination is malformed")
        if isinstance(expected_value, bool) or not isinstance(expected_value, int) or expected_value < 0:
            raise ValueError("signed EVM transaction value is malformed")
        if not isinstance(expected_data, str) or not _HEX_DATA.fullmatch(expected_data):
            raise ValueError("signed EVM transaction calldata is malformed")
        if enrollment["network"] != str(action.get("network") or "").lower():
            raise PermissionError("enrolled network does not match signed authorization")
        if str(submission.get("network") or "").lower() != enrollment["network"]:
            raise PermissionError("wallet submission network does not match enrollment")

        try:
            issuer_raw = base64.b64decode(enrollment["issuer_public_key_b64"], validate=True)
            issuer_public_key = Ed25519PublicKey.from_public_bytes(issuer_raw)
        except (ValueError, TypeError):
            raise ValueError("enrolled installation issuer key is invalid") from None
        executed_at = receipt_payload.get("executed_at")
        if isinstance(executed_at, bool) or not isinstance(executed_at, int):
            raise ValueError("signed wallet receipt execution timestamp is malformed")
        # Authorization TTL is evaluated at the issuer-signed wallet hand-off
        # time, not at delayed backend ingestion time. This permits safe retries
        # after a network outage without accepting a receipt for an expired grant.
        valid, reason = verify_execution_authorization(
            authorization, issuer_public_key, verification_time=executed_at,
        )
        if not valid:
            raise PermissionError(f"installation authorization signature is invalid at wallet submission: {reason}")
        valid, reason = verify_execution_receipt(receipt, issuer_public_key, authorization)
        if not valid:
            raise PermissionError(f"wallet execution receipt signature or binding is invalid: {reason}")

        if receipt_payload.get("network") != enrollment["network"]:
            raise ValueError("receipt network does not match enrolled network")
        submitted_to = submission.get("to")
        expected_to = expected_tx.get("to")
        if not isinstance(submitted_to, str) or not _EVM_ADDRESS.fullmatch(submitted_to) or submitted_to.lower() != expected_to.lower():
            raise ValueError("wallet receipt destination does not match signed authorization")
        submitted_value = submission.get("value_wei")
        expected_value = expected_tx.get("value_wei")
        if (
            isinstance(submitted_value, bool) or not isinstance(submitted_value, int)
            or isinstance(expected_value, bool) or not isinstance(expected_value, int)
            or submitted_value != expected_value
        ):
            raise ValueError("wallet receipt value does not match signed authorization")
        expected_calldata_sha256 = hashlib.sha256(expected_data.lower().encode("utf-8")).hexdigest()
        if submission.get("calldata_sha256") != expected_calldata_sha256:
            raise ValueError("wallet receipt calldata does not match signed authorization")
        tx_hash = receipt_payload.get("transaction_ref")
        if not isinstance(tx_hash, str) or not _EVM_HASH.fullmatch(tx_hash):
            raise ValueError("wallet receipt transaction hash is malformed")

        persisted = self.storage.record_external_execution_submission(authorization, receipt)
        return {
            "status": "STORED", "authorization_id": auth_payload["authorization_id"],
            "installation_principal": principal, "enrollment_id": enrollment["enrollment_id"],
            "transaction_hash": tx_hash, "receipt_sha256": hashlib.sha256(
                json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(), **persisted,
        }
