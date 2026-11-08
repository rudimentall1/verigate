# Anna Wallet Enrollment and Chain Receipt Ingestion

**Status:** backend foundation implemented on `feat/governed-wallet-enrollment`; not merged, deployed, or integrated into the Anna UI/Executa hand-off yet.

## Problem being closed

Anna Executa creates an installation-signed `SUBMITTED` `ExecutionReceipt` in its own local storage. The independent Verigate API has a different storage boundary and cannot verify that receipt by looking only in its own database. The API also cannot safely use its own issuer key to verify receipts signed by an Anna installation key.

This change adds an explicit trust and evidence-transfer contract. It does not claim that an independent chain verifier is already running.

## Trust model and invariants

1. An Anna installation principal is `anna-installation:<sha256(raw Ed25519 issuer public key)>`. The issuer public key is public; the private key never leaves Executa.
2. A wallet enrollment binds one installation principal, issuer key fingerprint/public key, EVM chain ID, network label, wallet address and minimum confirmation count.
3. Wallet enrollment and revocation require a governance-signed action and a governance quorum. The HTTP API refuses wallet changes when the configured quorum threshold is below 2. Production governance policy must explicitly allow `WALLET_ENROLL` and `WALLET_REVOKE`.
4. Governance approval is the trust decision for wallet ownership. Operators must independently verify control of the wallet before approving enrollment. This implementation does not pretend that a caller-supplied address proves ownership; a future wallet-signature challenge can automate this operational check.
5. Only an active enrolled wallet can submit evidence for its installation and chain. An active `(chain_id, wallet_address)` cannot be assigned to a second installation in the same tenant. Reassignment requires governance revocation first.
6. The ingestion API verifies the installation-signed ExecutionAuthorization and signed `SUBMITTED` ExecutionReceipt against the issuer key stored in that enrollment. Authorization expiry is evaluated at the signed receipt's `executed_at`, not delayed backend ingestion time, so network retries do not invalidate a hand-off that was valid when it occurred.
7. Submission persistence is atomic and idempotent. Exact retries succeed; a different receipt for the same authorization is rejected.
8. A CHAIN_VERIFIER attestation for an Anna installation is accepted only while its wallet enrollment is active. It is checked using the enrolled issuer key, and the attestation must bind to the stored authorization and original `SUBMITTED` receipt.
9. A verified outcome records Dynamic Authority events against the canonical installation principal and capability ID from the signed authorization. Display labels do not select the authority scope.

## API contract added

All routes are subject to the existing API-key middleware. Production must configure tenant API keys or `VERIGATE_API_KEYS` and set `VERIGATE_REQUIRE_AUTH=1` where appropriate.

### Govern wallet enrollment

`POST /v1/governance/wallet-enrollments`

Request body contains a governance `action` and signed `approvals`. Actions:

- `WALLET_ENROLL`: issuer public key, EVM chain ID, network, wallet address, minimum confirmations and enrollment ID.
- `WALLET_REVOKE`: existing enrollment ID.

The service derives the installation principal and key fingerprint from the supplied raw Ed25519 public key; caller-supplied principal/key fingerprints must match. Changes and their governance envelope are committed atomically.

`GET /v1/governance/wallet-enrollments/{installation_principal}` returns the public enrollment records and governance history.

### Transfer the signed wallet receipt

`POST /v1/execution/submissions`

Request body:

```json
{
  "authorization": { "payload": {}, "signature": "...", "algorithm": "Ed25519" },
  "execution_receipt": { "payload": {}, "signature": "...", "algorithm": "Ed25519" }
}
```

The API checks the principal, active enrolled sender and chain, issuer signature, receipt signature, `SUBMITTED` state, transaction hash, destination, value and calldata fingerprint before persisting the authorization/receipt pair.

`GET /v1/execution/submissions/{authorization_id}` returns the signed authorization, signed wallet receipt and active enrollment to an authenticated verifier worker. It does not expose private keys.

### Submit the independent outcome

`POST /v1/outcomes/attest` remains the attestation endpoint. A CHAIN_VERIFIER key must be registered through the existing governance-controlled attestor lifecycle. For Anna installation principals, outcome verification resolves the issuer key through the active wallet enrollment instead of assuming the API's own issuer key.

`WalletEnrollmentService.evm_verifier_for_wallet(...)` constructs `EVMChainVerifier` using the enrolled sender and confirmation threshold; the caller must not choose either value from transaction input.

## Security / failure behavior

- Unknown or revoked wallet: reject.
- One governance approval when threshold is 2: reject.
- Wrong issuer key, wrong principal, wrong chain/network, sender mismatch, malformed EVM envelope, tampered receipt, conflicting duplicate: reject.
- Ingestion outage: caller may retry the exact signed authorization/receipt; authorization validity is checked at signed execution time.
- Below configured confirmation depth: EVM verifier reports `UNKNOWN`/pending, not success.
- Reorg after a successful attestation is not automatically reversed yet. Confirmation depth reduces risk; it is not finality monitoring.
- The external verifier must run with a separate CHAIN_VERIFIER private key, distinct from both the installation issuer key and governance key.

## What is still missing before this becomes an active product flow

- Anna Executa currently does **not** call `POST /v1/execution/submissions` after persisting its local receipt. Add an explicit, authenticated verifier-backend configuration and invoke this endpoint with bounded retries; do not put API secrets in tool arguments or UI-visible data.
- A one-shot independent worker is now implemented at `scripts/chain_verifier_worker.py`. It fetches the authenticated submission and governed attestor record, verifies the installation authorization and wallet receipt locally, checks that its separate private key matches the governed CHAIN_VERIFIER public key, resolves the pinned sender/finality threshold from the enrollment, queries EVM RPC, signs the OutcomeAttestation and posts it to `/v1/outcomes/attest`.
- Run it with `VERIGATE_VERIFIER_API_URL`, `VERIGATE_VERIFIER_API_KEY`, `VERIGATE_CHAIN_RPC_URL`, optional `VERIGATE_TENANT_ID`, and the existing `VERIGATE_KEY_PASSPHRASE` for an encrypted attestor key. The API key is read from the environment, never from command-line arguments. Example: `python scripts/chain_verifier_worker.py --authorization-id <authorization-id> --attestor-id <governed-attestor-id> --attestor-key <private-key-path>`.
- The worker is one-shot for a single authorization. A durable queue, scheduler/lease, worker deployment, RPC failover and unattended retries are not implemented. The chain evidence reference is stable per chain/transaction, so repeated attestations for the same transaction do not count as multiple Dynamic Authority successes.
- Wallet ownership is approved out-of-band by governance; add a wallet-signature challenge before automating self-service enrollment.
- EVM only. Solana outcome claims are not supported by the current CHAIN_VERIFIER claim validator.
- Reorg monitoring/reversal, production RPC failover/rate limits, load tests and live Anna Cloud lifecycle acceptance remain outstanding.

## Local verification

The focused suite covers governed enrollment/revocation, quorum enforcement, active wallet uniqueness/reassignment, trusted verifier construction, cross-storage receipt ingestion, delayed ingestion after authorization TTL, idempotent retries, tamper rejection, authenticated submission retrieval, the one-shot worker's EVM receipt observation, CHAIN_VERIFIER attestation, and deduplication of Dynamic Authority success events across repeated observations. Full repository test results are recorded in the PR after the final run.
