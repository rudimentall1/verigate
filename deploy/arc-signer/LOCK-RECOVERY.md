# Arc signer journal lock recovery

This procedure removes only a provably stale `.lock` file. It does not repair, truncate, rewrite or delete journal records, and it does not authorize retrying an unresolved operation.

## Preconditions

1. Run this on the signer host as the signer account that owns the journal and lock.
2. Confirm the corresponding signer systemd instance is stopped or inactive. Do not stop unrelated services.
3. Do not use `rm` on the lock file. Do not edit the journal by hand.
4. If the signer process is still alive, recovery must refuse. Investigate the service instead.

## Inspect first

From the repository root:

```sh
node scripts/recover_arc_signer_lock.mjs /absolute/path/to/operations.jsonl
```

Expected outcomes:

- `status: absent`: no lock file exists; no action is needed.
- `status: live`: the recorded PID, boot ID and process start ticks still identify a live process. Do not recover.
- `status: stale`: the recorded owner is provably gone, the host boot ID changed, or the PID now belongs to a different process start time. Review the reason and confirm the service is inactive.

The command refuses symlinks, hard links, unexpected ownership, permissions other than 0600, malformed metadata, and cases where process identity cannot be established.

## Explicit recovery

Only after the inspection returns `status: stale` and the service is confirmed inactive:

```sh
node scripts/recover_arc_signer_lock.mjs /absolute/path/to/operations.jsonl --apply
```

The command rechecks the lock inode before unlinking it. It removes the lock file only. It does not touch the journal.

## After recovery: do not replay unresolved operations

Inspect the journal without modifying it:

```sh
cat /absolute/path/to/operations.jsonl
```

- A `reserved` record means the process died before a transaction hash was durably recorded. The RPC outcome may still be ambiguous. Do not retry automatically.
- A `broadcast` record includes a durable transaction hash. Check the Arc transaction/receipt and reconcile the result before any manual state repair.
- A `complete` record is already settled in the local journal and must remain intact.

If an operation is unresolved, keep the signer stopped until an operator has established whether a transaction was broadcast and whether it was mined. Lock recovery is not transaction reconciliation and does not clear replay protection.

## Safety boundary

Never delete or recreate the journal to clear an operation. Never automatically remove stale locks during daemon startup. Never treat this procedure as approval to provision keys, start production signers, or send a live transaction.


## Transaction reconciliation after an ambiguous RPC outcome

Lock recovery and transaction reconciliation are separate operations. Removing a provably stale lock does not make an unresolved reservation safe to retry.

### Read-only journal inspection

From the repository root, run:

```sh
node scripts/inspect_arc_signer_journal.mjs /absolute/path/to/operations.jsonl
```

The command validates the journal file using the same ownership, link-count and permission checks as the signer, validates operation-state transitions, and prints the latest state per authorization/operation. It is read-only. Exit code 3 means at least one operation remains unresolved; exit code 1 means inspection was refused or the journal is invalid.

### Required operator sequence

1. Keep the affected signer instance stopped. Confirm no request handler or signer process is still running. Do not stop unrelated services.
2. Preserve a byte-for-byte copy of the journal and relevant service/RPC logs for incident review. Do not edit the active journal by hand.
3. Recover a stale lock only through the inspect-first/explicit-apply procedure above. Do not remove a live lock.
4. Load the exact signed authorization and pinned signer configuration associated with the journal entry. Re-derive the only valid transaction for that role and operation. Do not trust calldata, destination or amount copied from an untrusted request or log.
5. Query the configured Arc Mainnet RPC (chain ID 5042) and, where available, a second independent Arc RPC/explorer. Record the endpoint, query time, signer address and nonce observations. Do not expose private keys.

### If the latest journal state is `broadcast`

The journal contains a durable transaction hash. Query both the transaction and receipt for that exact hash.

Before considering it settled, verify all of the following against the derived operation and pinned configuration:

- chain ID is 5042;
- transaction hash matches the journal;
- sender is the configured signer for the journal role;
- nonce matches the transaction and signer history;
- destination, calldata, native value and transaction type/fee fields match the derived operation and configured limits;
- receipt transaction hash matches, status is successful, block number/hash are present and the inclusion is finalized according to Arc's supported finality evidence;
- actual native fee is within the reservation ceiling and the role's daily budget accounting remains valid.

A pending transaction, missing receipt, unavailable RPC, pruned history, inconsistent endpoints, reverted receipt, or any mismatch remains unresolved. Do not rebroadcast. A reverted transaction is not a successful completion; preserve the record and escalate for explicit operator review.

### If the latest journal state is `reserved`

There is no durably recorded transaction hash. This is the most ambiguous case: the process may have submitted the transaction and crashed before persisting the returned hash.

- Search the signer address's transaction history and pending pool for the exact nonce and expected transaction. Compare sender, nonce, destination, calldata and value with the independently derived operation.
- Inspect the signer account's pending and latest nonce, and account for every transaction at or after the reservation window. A nonce increase alone does not identify which transaction consumed it.
- Use a second independent RPC or explorer when available. Record the evidence and any provider limitations.
- If an exact matching transaction is found, treat it as an unresolved broadcast and follow the `broadcast` verification procedure. Do not retry while it is pending or until its receipt/finality is established.
- If no transaction is found but nonce/history evidence is incomplete, inconsistent or pruned, the result is still ambiguous. Keep the signer stopped and the reservation blocked.
- Absence from one RPC's transaction-pool response is not proof that no broadcast occurred. Never clear or retry a `reserved` entry based only on a missing transaction hash or a single `eth_getTransactionByHash` miss.

### Resolution boundary

The current journal inspector is deliberately read-only. It does not append a `complete`, `failed` or `aborted` record, alter budgets, clear replay protection, or authorize a new transaction. There is no automated recovery command for unresolved operation states.

If the outcome cannot be established conclusively, preserve the unresolved entry and escalate. Any future state-transition tooling must be separately reviewed, append-only, require explicit operator evidence and approval, and prove that it cannot turn an uncertain broadcast into a second payment. Do not create a new authorization or retry the same economic action merely to bypass a blocked journal entry.
