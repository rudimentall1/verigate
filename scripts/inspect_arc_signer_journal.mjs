#!/usr/bin/env node
/**
 * Read-only audit of Arc signer journal operation states.
 *
 * This command never mutates the journal and never resolves or retries an operation.
 * Usage: node scripts/inspect_arc_signer_journal.mjs /path/to/operations.jsonl
 */
import { resolve } from "node:path";
import { lstatSync } from "node:fs";
import { OperationJournal } from "../integrations/arc-constrained-signer.mjs";

const args = process.argv.slice(2);
if (args.length !== 1 || args[0] === "--help" || args[0] === "-h") {
  console.log("Usage: node scripts/inspect_arc_signer_journal.mjs /path/to/operations.jsonl");
  console.log("Read-only. Unresolved records remain blocked; no transaction is rebroadcast.");
  process.exitCode = args.length === 1 ? 0 : 2;
} else {
  try {
    const path = resolve(args[0]);
    try { lstatSync(path); }
    catch (error) {
      if (error.code === "ENOENT") throw new Error("journal file does not exist; refusing to report an empty journal");
      throw error;
    }
    const rows = new OperationJournal(path).records();
    const grouped = new Map();
    for (const row of rows) {
      if (!row || typeof row !== "object"
        || typeof row.authorizationId !== "string"
        || typeof row.operation !== "string"
        || !["register", "consume", "payment"].includes(row.operation)
        || !["reserved", "broadcast", "complete"].includes(row.state)) {
        throw new Error("journal contains an invalid operation record; refusing to summarize");
      }
      const key = (row.authorizationKey ?? row.authorizationId) + ":" + row.operation;
      const events = grouped.get(key) ?? [];
      events.push(row);
      grouped.set(key, events);
    }

    const operations = [];
    for (const events of grouped.values()) {
      let previous;
      for (const row of events) {
        if (!previous && row.state !== "reserved") {
          throw new Error("journal operation does not begin with a reservation; refusing to summarize");
        }
        if (previous?.state === "reserved" && row.state !== "broadcast") {
          throw new Error("invalid journal transition after reserved state; refusing to summarize");
        }
        if (previous?.state === "broadcast"
          && (row.state !== "complete" || row.txHash?.toLowerCase() !== previous.txHash?.toLowerCase())) {
          throw new Error("invalid journal transition after broadcast state; refusing to summarize");
        }
        if (previous?.state === "complete") {
          throw new Error("journal contains events after a completed operation; refusing to summarize");
        }
        if (row.state === "broadcast" && !/^0x[0-9a-fA-F]{64}$/.test(row.txHash ?? "")) {
          throw new Error("broadcast record has an invalid transaction hash; refusing to summarize");
        }
        previous = row;
      }
      const latest = events.at(-1);
      const unresolved = latest.state !== "complete";
      let operatorAction = "No action. Preserve the completed journal record.";
      if (latest.state === "reserved") {
        operatorAction = "AMBIGUOUS: no durable tx hash. Do not retry. Absence of a hash is not proof that broadcast did not occur; reconcile signer nonce, pending pool and chain history.";
      } else if (latest.state === "broadcast") {
        operatorAction = "UNRESOLVED: inspect this exact tx hash and receipt. Verify chain, sender, nonce, destination, calldata, value, receipt status and finality. Do not retry while pending or ambiguous.";
      }
      operations.push({
        authorizationId: latest.authorizationId,
        operation: latest.operation,
        state: latest.state,
        txHash: latest.txHash ?? null,
        reservedNativeCost: latest.reservedNativeCost ?? null,
        actualNativeCost: latest.actualNativeCost ?? null,
        eventCount: events.length,
        unresolved,
        operatorAction,
      });
    }
    operations.sort((a, b) => a.authorizationId.localeCompare(b.authorizationId) || a.operation.localeCompare(b.operation));
    console.log(JSON.stringify({
      mode: "read-only",
      journal: path,
      recordCount: rows.length,
      unresolvedCount: operations.filter(x => x.unresolved).length,
      operations,
      warning: "This report does not query Arc RPC, prove transaction absence, reconcile state, or authorize rebroadcast.",
    }, null, 2));
    if (operations.some(x => x.unresolved)) process.exitCode = 3;
  } catch (error) {
    console.error("Journal inspection refused:", error.message);
    process.exitCode = 1;
  }
}
