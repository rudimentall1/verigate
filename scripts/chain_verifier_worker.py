"""One-shot independent EVM chain verifier for an ingested Anna wallet submission.

Required environment:
  VERIGATE_VERIFIER_API_URL   HTTPS base URL of the authenticated Verigate API
  VERIGATE_VERIFIER_API_KEY   API key (never pass it on the command line)
  VERIGATE_CHAIN_RPC_URL      HTTPS JSON-RPC endpoint for the enrolled chain
  VERIGATE_TENANT_ID          Optional tenant header when tenant-key mode is enabled
  VERIGATE_KEY_PASSPHRASE     Optional passphrase for the CHAIN_VERIFIER key file
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from attest.keys import load_private_key
from attest.receipt import verify_execution_authorization, verify_execution_receipt
from core.outcome import (
    build_outcome_attestation,
    build_outcome_claim,
    digest,
    key_fingerprint,
)
from core.wallet_enrollment import installation_principal
from enforcement.chain_verification import EVMChainVerifier
from enforcement.evm_rpc import EvmRpcClient, EvmRpcError


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def create_chain_attestation(
    submission: dict[str, Any],
    *,
    attestor_id: str,
    attestor_private_key,
    rpc: EvmRpcClient,
    observed_at: float | None = None,
) -> dict[str, Any]:
    """Create a deterministic-claim CHAIN_VERIFIER attestation from API evidence."""
    try:
        authorization = submission["authorization"]
        receipt = submission["execution_receipt"]
        enrollment = submission["wallet_enrollment"]
        auth_payload = authorization["payload"]
        receipt_payload = receipt["payload"]
        enrollment_id = enrollment["enrollment_id"]
        principal = auth_payload["agent_id"]
        chain_id = enrollment["chain_id"]
        wallet_address = enrollment["wallet_address"]
        min_confirmations = enrollment["min_confirmations"]
        transaction_hash = receipt_payload["transaction_ref"]
        submission_data = receipt_payload["submission_data"]
        issuer_public_key_b64 = enrollment["issuer_public_key_b64"]
    except (KeyError, TypeError):
        raise ValueError("API submission is missing required signed evidence or enrollment fields") from None

    if submission.get("authorization_id") != auth_payload.get("authorization_id"):
        raise ValueError("API submission authorization ID mismatch")
    if enrollment.get("status") != "ACTIVE":
        raise PermissionError("wallet enrollment is not active")
    if enrollment.get("installation_principal") != principal:
        raise PermissionError("wallet enrollment principal does not match signed authorization")
    if enrollment.get("chain_id") != receipt_payload.get("submission_data", {}).get("chain_id"):
        raise PermissionError("wallet enrollment chain does not match signed wallet receipt")
    if receipt_payload.get("network") != enrollment.get("network"):
        raise PermissionError("wallet enrollment network does not match signed wallet receipt")
    if receipt_payload.get("status") != "SUBMITTED":
        raise ValueError("CHAIN_VERIFIER only accepts the original SUBMITTED wallet receipt")
    if not isinstance(transaction_hash, str):
        raise ValueError("wallet receipt transaction hash is missing")
    try:
        issuer_raw = base64.b64decode(issuer_public_key_b64, validate=True)
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        issuer_public_key = Ed25519PublicKey.from_public_bytes(issuer_raw)
    except (ValueError, TypeError):
        raise ValueError("enrolled installation issuer public key is malformed") from None
    derived_principal, issuer_key_id = installation_principal(issuer_public_key_b64)
    if derived_principal != principal or issuer_key_id != enrollment.get("issuer_key_id"):
        raise PermissionError("enrollment issuer key does not derive the signed installation principal")
    executed_at = receipt_payload.get("executed_at")
    if isinstance(executed_at, bool) or not isinstance(executed_at, int):
        raise ValueError("signed wallet receipt execution timestamp is malformed")
    valid, reason = verify_execution_authorization(
        authorization, issuer_public_key, verification_time=executed_at,
    )
    if not valid:
        raise PermissionError(f"installation authorization signature is invalid: {reason}")
    valid, reason = verify_execution_receipt(receipt, issuer_public_key, authorization)
    if not valid:
        raise PermissionError(f"wallet receipt signature or authorization binding is invalid: {reason}")
    if (
        not isinstance(submission_data, dict)
        or str(submission_data.get("sender", "")).lower() != str(wallet_address).lower()
        or submission_data.get("chain_id") != chain_id
        or str(submission_data.get("network", "")).lower() != str(enrollment.get("network", "")).lower()
    ):
        raise PermissionError("signed wallet submission metadata does not match enrollment")

    verifier = EVMChainVerifier(
        expected_sender=wallet_address,
        min_confirmations=min_confirmations,
    )
    observed = verifier.verify_receipt(
        authorization,
        rpc,
        transaction_hash=transaction_hash,
        evidence_ref=f"evm:{chain_id}:{transaction_hash.lower()}",
        observed_at=observed_at,
    )
    claim_id = digest({
        "authorization_id": auth_payload["authorization_id"],
        "attestor_id": attestor_id,
        "observed_effect_sha256": digest(observed.as_dict()),
    })
    claim = build_outcome_claim(
        receipt,
        status=observed.effect_status,
        executor_id=receipt_payload["executor"],
        evidence_kind="CHAIN_RECEIPT",
        evidence_ref=observed.evidence_ref,
        result_sha256=observed.result_sha256,
        observed_effect=observed.as_dict(),
        observed_at=observed_at,
        claim_id=claim_id,
        metadata={
            "enrollment_id": enrollment_id,
            "chain_id": chain_id,
            "required_confirmations": min_confirmations,
        },
    )
    return build_outcome_attestation(
        claim,
        attestor_id=attestor_id,
        attestor_type="CHAIN_VERIFIER",
        private_key=attestor_private_key,
    )


def _api_request(base_url: str, api_key: str, tenant_id: str | None, path: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = _canonical(payload)
    if tenant_id:
        headers["X-Verigate-Tenant"] = tenant_id
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        raise RuntimeError(f"Verifier API returned HTTP {exc.code}: {detail}") from None
    except (urllib.error.URLError, OSError):
        raise RuntimeError("Verifier API request failed; check URL, TLS and connectivity") from None
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise RuntimeError("Verifier API returned invalid JSON") from None
    if not isinstance(result, dict):
        raise RuntimeError("Verifier API returned an unexpected response")
    return result


def _require_secure_endpoint(value: str, name: str) -> None:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError(f"{name} must use HTTPS outside localhost")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{name} must be an absolute HTTP(S) URL")


def run_once(authorization_id: str, attestor_id: str, attestor_key_path: str) -> dict[str, Any]:
    api_url = os.environ.get("VERIGATE_VERIFIER_API_URL", "").strip()
    api_key = os.environ.get("VERIGATE_VERIFIER_API_KEY", "").strip()
    rpc_url = os.environ.get("VERIGATE_CHAIN_RPC_URL", "").strip()
    tenant_id = os.environ.get("VERIGATE_TENANT_ID", "").strip() or None
    if not api_url or not api_key or not rpc_url:
        raise ValueError("VERIGATE_VERIFIER_API_URL, VERIGATE_VERIFIER_API_KEY and VERIGATE_CHAIN_RPC_URL are required")
    _require_secure_endpoint(api_url, "VERIGATE_VERIFIER_API_URL")
    _require_secure_endpoint(rpc_url, "VERIGATE_CHAIN_RPC_URL")

    attestor = _api_request(
        api_url, api_key, tenant_id,
        f"/v1/governance/attestors/{urllib.parse.quote(attestor_id, safe='')}",
    ).get("attestor")
    if (
        not isinstance(attestor, dict)
        or attestor.get("attestor_id") != attestor_id
        or attestor.get("status") != "ACTIVE"
        or attestor.get("attestor_type") != "CHAIN_VERIFIER"
    ):
        raise PermissionError("configured attestor is not an active CHAIN_VERIFIER")
    private_key = load_private_key(attestor_key_path)
    if key_fingerprint(private_key.public_key()) != attestor.get("key_id"):
        raise PermissionError("local CHAIN_VERIFIER private key does not match governed public key")

    submission = _api_request(
        api_url, api_key, tenant_id,
        f"/v1/execution/submissions/{urllib.parse.quote(authorization_id, safe='')}",
    )
    rpc = EvmRpcClient(rpc_url)
    attestation = create_chain_attestation(
        submission,
        attestor_id=attestor_id,
        attestor_private_key=private_key,
        rpc=rpc,
    )
    response = _api_request(
        api_url, api_key, tenant_id,
        "/v1/outcomes/attest", method="POST", payload={"attestation": attestation},
    )
    return {
        "valid": response.get("valid"),
        "authorization_id": authorization_id,
        "transaction_hash": submission["execution_receipt"]["payload"]["transaction_ref"],
        "outcome_status": attestation["payload"]["claim"]["status"],
        "attestation_id": response.get("attestation_id"),
        "authority_event": response.get("authority_event"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify one ingested Anna EVM wallet submission and post a CHAIN_VERIFIER attestation.")
    parser.add_argument("--authorization-id", required=True, help="64-character Verigate authorization ID")
    parser.add_argument("--attestor-id", required=True, help="Governance-registered CHAIN_VERIFIER ID")
    parser.add_argument("--attestor-key", required=True, help="Path to the separate CHAIN_VERIFIER Ed25519 private key")
    args = parser.parse_args()
    try:
        result = run_once(args.authorization_id, args.attestor_id, args.attestor_key)
    except EvmRpcError:
        print("ERROR: EVM RPC verification failed; check RPC availability and configuration", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result.get("valid") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
