# Wallet Governance Transparency Log v1

## Purpose

The wallet governance history inside a Verigate proof is signed and hash-bound, but those properties alone do not prove that the proof contains every governance action that was ever accepted. An operator able to roll back the source database could remove a later \`WALLET_REVOKE\`, restore an earlier registry snapshot, and rebuild a self-consistent but stale proof.

This protocol adds a separately administered transparency log. It records the full signed governance envelope for every accepted wallet action in a per-installation append-only hash chain. The log issues an Ed25519-signed checkpoint over the current chain head, entry count and canonical wallet-history digest.

## Trust model

The external log is a separate security boundary, not another table in the Verigate database.

- The log database MUST be stored outside the writable Verigate data directory.
- The Ed25519 log signing key MUST be controlled by the log operator, not by the Verigate process. Prefer a KMS/HSM or a separately permissioned host/service.
- The log public key MUST be provisioned to offline verifiers through an independent trusted channel.
- The latest checkpoint SHA-256 MUST also be distributed independently of the proof. A public key by itself verifies authenticity, not freshness. The exact checkpoint digest prevents an older, once-valid checkpoint from being substituted after a newer checkpoint has been issued.
- The log operator MUST receive each accepted \`WALLET_ENROLL\` / \`WALLET_REVOKE\` envelope before treating that governance transition as committed for proof purposes. Backfilling only from a potentially rolled-back Verigate database cannot establish completeness.
- The proof issuer MUST include the log's exported bundle; the verifier MUST NOT fetch the log over the network. Verification remains offline.

The SQLite writer installs triggers that reject ordinary \`UPDATE\` and \`DELETE\` statements. These triggers are an operational safeguard, not a security boundary against the database administrator: an administrator can replace the database or remove triggers. The independent signing key and externally pinned latest checkpoint are the integrity and rollback trust anchors.

## Entry and checkpoint model

Each per-principal entry contains:

- log protocol and log identity;
- installation principal;
- monotonically increasing sequence number;
- previous entry digest (all-zero digest for the first entry);
- action ID and canonical envelope digest;
- complete signed governance envelope.

The entry digest is SHA-256 over canonical JSON of the entry payload. The next entry includes that digest as its predecessor.

Each checkpoint signs a payload containing the log identity, installation principal, checkpoint sequence, entry count, latest entry digest, canonical wallet-history digest, previous checkpoint digest, issue time and signer key fingerprint. The checkpoint digest is SHA-256 over the canonical checkpoint payload; the Ed25519 signature covers that same payload.

The wallet-history digest is calculated over canonical JSON of the complete envelope array sorted by \`action.action_id\` in ascending lexical order. The hash-chain sequence instead preserves the order in which the independent log accepted entries. This separation makes the history fingerprint deterministic while retaining an auditable append order.

The writer rejects a current history that omits a previously logged action or rewrites an existing action ID. Re-submitting an identical history is idempotent; new actions extend the entry chain and produce a new checkpoint.

## Reference writer

\`core.wallet_governance_transparency.WalletGovernanceTransparencyLog\` is the reference writer. Run it from a separately administered process with its own database and log signing key:

\`\`\`python
from core.wallet_governance_transparency import WalletGovernanceTransparencyLog

log = WalletGovernanceTransparencyLog(
    "/var/lib/independent-wallet-log/wallet-governance.sqlite3",
    log_id="production-wallet-governance-log",
    signing_key=log_signing_private_key,
)
log.export_public_key_pem("/etc/verigate-trust/wallet-governance-log.pub.pem")

# Preferred event-stream ingestion: one call for each accepted action.
bundle = log.append_envelope(installation_principal, accepted_governance_envelope)

# Bulk initial load or reconciliation from the independent log's own event store.
bundle = log.checkpoint_history(installation_principal, complete_governance_envelopes)
\`\`\`

The external log operator should retain the latest checkpoint digest and make it available to proof issuers and independent auditors over a separate authenticated channel. The private key must never be copied into the Verigate service or proof package.

### Reliable delivery from Verigate

`WalletEnrollmentService.apply` commits the wallet registry transition, signed governance envelope, and a `wallet_governance_outbox` row in the same local SQLite transaction. The outbox stores the complete envelope, accepted sequence, attempt count, last delivery error, and the signed checkpoint bundle returned by the external log.

Inject a `WalletGovernanceOutboxDispatcher` into the service to attempt synchronous delivery after the local commit:

```python
from core.wallet_enrollment import WalletEnrollmentService
from core.wallet_governance_outbox import WalletGovernanceOutboxDispatcher

dispatcher = WalletGovernanceOutboxDispatcher(
    storage,
    remote_log_transport,  # implements append_envelope(principal, envelope)
    trusted_log_public_key_b64=trusted_log_public_key_b64,
)
wallets = WalletEnrollmentService(
    storage,
    transparency_dispatcher=dispatcher,
)

result = wallets.apply(action, approvals, governance_policy)
# result["status"] is APPLIED only after signed external acknowledgement.
# A transport outage returns PENDING_TRANSPARENCY; the durable outbox remains.
```

Delivery is **at-least-once**, not exactly-once. A response may be lost after the remote log commits; the dispatcher retries the same action ID, so the transport endpoint MUST implement idempotent append semantics. Before marking an event `DELIVERED`, the dispatcher checks that the returned log entries are the exact locally accepted prefix and validates the signed checkpoint against the independently configured log public key.

A per-installation SQLite lease serializes workers across processes and expires after a crash. Dispatch pending events on startup and periodically with `dispatcher.dispatch_pending()`; `apply` also attempts delivery immediately. The caller must configure a bounded transport timeout shorter than the lease. Events are sent in local acceptance order; a failed event stops delivery of later actions for that installation until retry succeeds.

An enrollment remains locally recorded as `ACTIVE` while delivery is pending, but `WalletEnrollmentService.evm_verifier_for_wallet` refuses to construct a verifier until the corresponding `WALLET_ENROLL` outbox event is externally acknowledged. Revocations take effect locally immediately, even while external delivery is pending. Once a checkpoint is acknowledged, `EvidenceGraph` can attach the latest stored bundle automatically; an out-of-date checkpoint will fail against the complete current history.

The repository also provides a minimal authenticated HTTP endpoint and client adapter. Run the independent writer on loopback behind a TLS-terminating reverse proxy:

```bash
export VERIGATE_WALLET_GOVERNANCE_LOG_BEARER_TOKEN="<secret-from-secret-manager>"
python scripts/wallet_governance_log_service.py \
  --database /var/lib/independent-wallet-log/wallet-governance.sqlite3 \
  --log-id production-wallet-governance-log \
  --private-key /etc/wallet-log/signing-key.pem \
  --public-key-output /etc/wallet-log/wallet-governance-log.pub.pem
```

The reference server listens on `127.0.0.1:8765` by default, accepts authenticated `POST /v1/wallet-governance/append`, and exposes only a non-sensitive `GET /healthz` health check. Do not expose its plain-HTTP listener to an untrusted network. Terminate HTTPS at a reverse proxy, enforce rate limits there, and deliver the bearer token through a secret manager.

Configure Verigate with the HTTPS origin, same bearer token, and independently provisioned Ed25519 public key:

```python
from core.wallet_governance_transparency_http import WalletGovernanceTransparencyHTTPTransport
from core.wallet_governance_outbox import WalletGovernanceOutboxDispatcher
from core.wallet_enrollment import WalletEnrollmentService

transport = WalletGovernanceTransparencyHTTPTransport(
    "https://wallet-log.example.net",
    bearer_token=wallet_log_bearer_token,
    timeout=10,
)
dispatcher = WalletGovernanceOutboxDispatcher(
    storage,
    transport,
    trusted_log_public_key_b64=trusted_wallet_log_public_key_b64,
)
wallet_service = WalletEnrollmentService(
    storage,
    transparency_dispatcher=dispatcher,
)
```

Run the durable outbox worker as a separate process using the same local Verigate database, external log URL, public key and bearer token:

```bash
export VERIGATE_WALLET_GOVERNANCE_LOG_BEARER_TOKEN="<secret-from-secret-manager>"
python scripts/wallet_governance_outbox_worker.py \
  --database /var/lib/verigate/verigate.sqlite3 \
  --log-url https://wallet-log.example.net \
  --log-public-key /etc/verigate-trust/wallet-governance-log.pub.pem \
  --interval 5 \
  --timeout 10
```

Run this worker under a process supervisor (for example, systemd) with automatic restart. It performs an initial sweep on startup, then retries pending records periodically. `--once` performs a single sweep and exits non-zero if any event remains pending. The outbox lease coordinates the worker with delivery attempts made synchronously during `WalletEnrollmentService.apply`; multiple worker instances are safe to run, although a second worker for the same installation will report `BUSY` while another holds its lease.

The HTTP client refuses plain HTTP except to loopback addresses, disables redirects to avoid forwarding credentials to another host, applies bounded request/response sizes, and uses a finite timeout. Keep the transport timeout below the outbox lease duration. The HTTP service and local SQLite writer are a reference deployment; production still needs TLS/reverse-proxy configuration, secret rotation, operational monitoring, backups, and independent checkpoint distribution.

Until the external log receives every accepted action and its latest checkpoint is pinned by the offline verifier, the wallet transparency check is explicitly `pinned=false`.

## Proof attachment and verification

Pass the externally produced bundle to the evidence graph builder:

\`\`\`python
graph = EvidenceGraph(
    storage,
    issuer_public_key,
    wallet_governance_anchors={installation_principal: bundle},
)
\`\`\`

The graph contains a \`wallet_governance_transparency_log\` node and an \`ANCHORED_BY\` edge from the wallet history node. The standalone verifier checks the complete entry chain, envelope set, checkpoint fields, checkpoint digest and Ed25519 signature. To establish external trust and freshness, supply both the log public key and the latest checkpoint digest:

\`\`\`bash
python tools/verigate_proof_verifier.py proof.json \\
  --public-key issuer.pub \\
  --wallet-governance-log-public-key wallet-governance-log.pub.pem \\
  --trusted-wallet-governance-checkpoint-sha256 <latest-checkpoint-sha256>
\`\`\`

The two flags are a pair: supplying only one fails closed. The checkpoint digest must be refreshed from the independent log operator after each newly accepted action. If the proof contains no checkpoint while these pins are supplied, verification fails. If the proof carries a valid signed checkpoint but neither out-of-band value is supplied, the proof can still pass its cryptographic integrity checks, but the verifier reports \`wallet_governance_transparency_anchor.pinned=false\` / \`NOT PINNED\`.

The existing \`--trusted-wallet-governance-policy-sha256\` and \`--trusted-wallet-enrollment-history-sha256\` options remain available. The checkpoint anchor complements them: the policy pin authenticates the governor roster, the history digest pin authenticates an exact history snapshot, and the signed transparency checkpoint provides a sequenced external commitment that can detect stale-checkpoint replay.

## Limits

- This reference implementation is a local SQLite writer and protocol verifier, not a deployed multi-tenant log service. Production use needs an authenticated transport, operational monitoring, backup/replication, access controls, retention policy and key lifecycle.
- The log must observe governance actions at acceptance time. A log created later from an already compromised or rolled-back source database cannot prove that missing actions never existed.
- The signer key and latest checkpoint digest are out-of-band trust inputs. If the operator loses or compromises both, the system cannot independently establish log authenticity/freshness.
- Log-key rotation requires an explicit trust update by verifiers. Do not silently replace the key while retaining the same trust configuration.
- No public Merkle transparency monitor, gossip protocol, blockchain anchoring or third-party witness quorum is implemented in this change.
