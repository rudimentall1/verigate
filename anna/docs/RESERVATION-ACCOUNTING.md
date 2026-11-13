# Verigate reservation accounting

Status: implemented in source; test suite pending; not yet rebuilt or released as an Anna Executa binary.

## Accounting rule

The rolling 24-hour policy counter is active reserved capacity, not confirmed on-chain spend.

- A non-BLOCK payment authorization reserves its amount against the issuer-installation principal and asset.
- A persisted, signature-verified `REJECTED` receipt releases the reservation. The Anna adapter accepts this only for EIP-1193 error 4001 during `eth_sendTransaction`.
- A persisted, signature-verified `ABORTED` receipt releases the reservation only after the adapter verifies the consumed Router nonce and the app-scoped approval. The UI reports this only when the wallet request was not started.
- `UNKNOWN` remains reserved because a transaction may have been submitted despite the missing response.
- `SUBMITTED` remains reserved because a wallet-returned transaction hash is not chain settlement.
- `BLOCK` remains excluded from the reservation total.
- Legacy audit rows without a linked executable authorization or verified outcome remain reserved conservatively.

## Implementation

The reservation total is derived from the existing `audit_log`, `authorization_artifacts` and `execution_receipts` tables. No parallel ledger or mutable balance counter is introduced. The SQL excludes an audit row only when the same intent has a linked execution receipt whose persisted status is `REJECTED` or `ABORTED`.

The old `spent_today` method remains as a backward-compatible alias. Anna's policy summary exposes `rolling_24h_reserved`; `rolling_24h_spend` remains as a compatibility field with the same reservation semantics.

## Security boundary and limitations

The negative outcome receipt is an Ed25519-signed Anna installation self-report bound to a consumed one-time authorization and an app-scoped approval. It is not a wallet-signed statement and does not provide independent chain confirmation. A future independent settlement/reconciliation path must not release a reservation on a transaction hash alone; it must verify the transaction and terminal chain outcome.

If outcome receipt creation fails, the reservation stays active. This is intentional fail-closed behavior. No timeout automatically releases an ambiguous reservation.

## Required verification

- ALLOW authorization reserves capacity.
- REJECTED with EIP-1193 4001 releases capacity only after a valid persisted receipt.
- ABORTED after a proven pre-wallet abort releases capacity.
- UNKNOWN and SUBMITTED remain reserved.
- Forged, unapproved, mismatched or conflicting receipts do not change accounting.
- Repeated exact receipt retries are idempotent.
