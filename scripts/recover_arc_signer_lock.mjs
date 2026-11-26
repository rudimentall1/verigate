#!/usr/bin/env node
/**
 * Inspect or explicitly recover a stale Arc signer journal lock.
 *
 * This command never edits journal records and never runs automatically.
 * Usage:
 *   node scripts/recover_arc_signer_lock.mjs /path/to/journal.jsonl
 *   node scripts/recover_arc_signer_lock.mjs /path/to/journal.jsonl --apply
 */
import { resolve } from "node:path";
import { OperationJournal } from "../integrations/arc-constrained-signer.mjs";

const args = process.argv.slice(2);
const apply = args.includes("--apply");
const positional = args.filter(value => value !== "--apply");
if (args.includes("--help") || args.includes("-h") || positional.length !== 1) {
  console.log("Usage: node scripts/recover_arc_signer_lock.mjs /path/to/journal.jsonl [--apply]");
  console.log("Without --apply, this command only inspects. Recovery requires a provably stale Linux process identity.");
  process.exitCode = positional.length === 1 ? 0 : 2;
} else {
  try {
    const journal = new OperationJournal(resolve(positional[0]));
    const result = journal.recoverStaleLock({ apply });
    console.log(JSON.stringify({
      ...result,
      owner: result.owner ? {
        pid: result.owner.pid,
        bootId: result.owner.bootId,
        startTicks: result.owner.startTicks,
      } : undefined,
    }, null, 2));
    if (result.status === "live") process.exitCode = 2;
  } catch (error) {
    console.error("Lock recovery refused:", error.message);
    process.exitCode = 1;
  }
}
