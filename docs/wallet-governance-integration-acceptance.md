# Wallet Governance Integration Acceptance Plan

## Purpose

This plan defines a controlled, repeatable acceptance run for the complete wallet-governance evidence path:

1. governance action is accepted and recorded locally;
2. the transactional outbox delivers the signed envelope;
3. the independent transparency service appends it idempotently;
4. the operator can reconcile local history against the remote hash chain and signed checkpoint.

This document is a test procedure, not evidence that a production deployment or end-to-end acceptance run has occurred. Execute it only against disposable test databases and an isolated service instance. Never use production wallet credentials, production signing keys, or live funds.

## Preconditions and test controls

- Use a dedicated test installation principal and synthetic governance actions.
- Use separate temporary SQLite databases for the application and transparency service.
- Generate a disposable Ed25519 log signing key and synthetic bearer tokens.
- Distribute the expected public key and checkpoint SHA-256 to the test operator through a channel independent of the test service and application database.
- Record software commit SHAs, test timestamps, configuration (excluding secrets), and sanitized command output.
- Keep the test service bound to loopback or an isolated network. If testing a non-loopback endpoint, use HTTPS with certificate verification enabled.
- Do not automatically advance trusted checkpoint pins during any test.
- Ensure all test databases and keys can be destroyed after evidence has been retained.

## Acceptance scenarios

### A. Baseline end-to-end delivery and reconciliation

1. Start with empty test databases and a fresh test principal.
2. Perform a valid synthetic wallet-governance enrollment through the normal application service path.
3. Confirm the local enrollment remains pending until the outbox delivery is acknowledged.
4. Run the outbox dispatcher against the isolated transparency service.
5. Confirm the outbox event becomes delivered and the remote log contains exactly one corresponding entry.
6. Independently obtain the service public key and checkpoint digest; run `scripts/wallet_governance_log_reconcile.py` with those pins.
7. Confirm exit code `0`, status `VERIFIED`, matching local/remote counts, and a pinned checkpoint verification.

**Pass:** enrollment activation follows the documented delivery rule; the event appears once; reconciliation verifies with independently supplied pins.

### B. Service outage and retry

1. Stop the isolated transparency service.
2. Create a valid synthetic governance event and run the dispatcher.
3. Confirm the event remains pending, with a recorded attempt and no false delivered state.
4. Restart the service and retry delivery.
5. Confirm eventual delivery and successful reconciliation.

**Pass:** transient unavailability does not lose the event or mark it delivered prematurely; retry succeeds without duplicate remote entries.

### C. Idempotent replay / unknown response

1. Submit the same signed envelope more than once, including a simulated lost response followed by a retry.
2. Inspect the remote bundle and checkpoint sequence.

**Pass:** replay does not create a second logical entry; the same accepted event resolves to the same idempotent result.

### D. Bearer-token overlap and retirement

1. Configure a new token and the old token as the previous token.
2. Verify both tokens can access the protected append and bundle endpoints during the overlap window.
3. Remove the old token from service configuration and restart the isolated service.
4. Verify the new token still works and the old token receives an authentication failure.

**Pass:** rotation has an explicit overlap window; retired credentials stop working; no token is printed in logs or reports.

### E. Authentication and transport rejection

Exercise missing, malformed, and incorrect bearer credentials; redirects; a non-HTTPS non-loopback URL; and a timeout.

**Pass:** unauthorized requests are rejected; credentials are not forwarded to redirect targets; insecure remote HTTP is refused; failures are reported as unhealthy without changing outbox delivery state.

### F. Tampered remote history

1. In a disposable copy of the transparency database, alter or remove an entry or checkpoint using a controlled test fixture.
2. Fetch and reconcile the altered bundle using the original independent public-key and checkpoint pins.

**Pass:** chain, signature, history, or pin verification fails; reconciliation exits non-zero and reports `UNHEALTHY`. Preserve the fixture and report as evidence.

### G. Stale checkpoint / rollback

1. Capture a valid checkpoint pin.
2. Advance the remote log with another synthetic event.
3. Attempt reconciliation using the old checkpoint pin.
4. Then obtain the new checkpoint digest independently and rerun.

**Pass:** the stale pin is rejected; the new independently approved pin verifies. The CLI never silently learns or updates a pin from the service response.

### H. Local database rollback or divergence

1. Back up the local test database after one delivered event.
2. Deliver a second event and capture the current remote checkpoint.
3. Restore the older local database backup.
4. Reconcile against the current remote bundle and current independently distributed checkpoint pin.

**Pass:** local/remote history mismatch is detected. Record the important limitation: this detects divergence when an independent current pin is available; it does not prove that a local database has never been rolled back if no independent checkpoint history or backup exists.

### I. Database and service failure reporting

Run reconciliation with a nonexistent database path, a corrupt SQLite file, an unreachable service, and an unknown installation principal.

**Pass:** the command exits non-zero and emits structured `UNHEALTHY` JSON; it does not emit a traceback containing secrets or mutate local/remote state.

### J. Response-size and concurrency boundaries

1. Exercise a remote bundle at and above the configured response-size limit.
2. Run concurrent append and bundle-read requests for the same principal.
3. Verify all returned bundles are internally consistent and no partial write is exposed.

**Pass:** oversized responses are rejected; concurrent reads serialize safely with writes; no malformed or partially committed bundle is accepted.

## Evidence record

For each scenario, retain:

- scenario ID and pass/fail result;
- application and service commit SHAs;
- UTC start/end timestamps;
- sanitized configuration and test topology;
- relevant test command and exit code;
- sanitized JSON output and remote bundle/checkpoint identifiers;
- any failure log and the corresponding issue reference.

Never retain bearer-token values, private signing keys, production identifiers, or wallet secrets in the evidence package.

## Exit criteria

The integration acceptance run is complete only when:

- all applicable scenarios A–J pass on an isolated environment;
- each failure case produces the expected fail-closed outcome;
- no scenario mutates trusted pins automatically;
- evidence is reproducible from the recorded commit SHAs and disposable fixtures;
- unresolved failures and limitations are explicitly documented.

A passing unit/CI suite alone does not satisfy these criteria. This plan does not authorize production deployment, live credential rotation, or any transfer of funds.
