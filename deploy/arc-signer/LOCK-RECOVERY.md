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
