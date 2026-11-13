import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const script = resolve("scripts/inspect_arc_signer_journal.mjs");

test("journal inspector reports unresolved reserved and broadcast states without mutation", () => {
  const dir = mkdtempSync(join(tmpdir(), "verigate-journal-inspect-"));
  try {
    const path = join(dir, "ops.jsonl");
    const rows = [
      { authorizationId: "aa", authorizationKey: "aa:key", operation: "consume", state: "reserved", at: 1 },
      { authorizationId: "bb", authorizationKey: "bb:key", operation: "payment", state: "reserved", at: 2 },
      { authorizationId: "bb", authorizationKey: "bb:key", operation: "payment", state: "broadcast", txHash: "0x" + "12".repeat(32), at: 3 },
      { authorizationId: "cc", authorizationKey: "cc:key", operation: "register", state: "reserved", at: 4 },
      { authorizationId: "cc", authorizationKey: "cc:key", operation: "register", state: "broadcast", txHash: "0x" + "34".repeat(32), at: 5 },
      { authorizationId: "cc", authorizationKey: "cc:key", operation: "register", state: "complete", txHash: "0x" + "34".repeat(32), result: { txHash: "0x" + "34".repeat(32) }, at: 6 },
    ];
    const original = rows.map(row => JSON.stringify(row)).join("\n") + "\n";
    writeFileSync(path, original, { mode: 0o600 });
    const result = spawnSync(process.execPath, [script, path], { encoding: "utf8" });
    assert.equal(result.status, 3, result.stderr);
    const report = JSON.parse(result.stdout);
    assert.equal(report.mode, "read-only");
    assert.equal(report.recordCount, 6);
    assert.equal(report.unresolvedCount, 2);
    assert.equal(report.operations.find(x => x.authorizationId === "aa").state, "reserved");
    assert.match(report.operations.find(x => x.authorizationId === "aa").operatorAction, /Absence of a hash is not proof/);
    assert.equal(report.operations.find(x => x.authorizationId === "bb").txHash, "0x" + "12".repeat(32));
    assert.equal(report.operations.find(x => x.authorizationId === "cc").state, "complete");
    assert.equal(readFileSync(path, "utf8"), original);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("journal inspector refuses invalid state transitions", () => {
  const dir = mkdtempSync(join(tmpdir(), "verigate-journal-inspect-invalid-"));
  try {
    const path = join(dir, "ops.jsonl");
    const rows = [
      { authorizationId: "dd", operation: "consume", state: "reserved" },
      { authorizationId: "dd", operation: "consume", state: "complete", txHash: "0x" + "56".repeat(32) },
    ];
    writeFileSync(path, rows.map(row => JSON.stringify(row)).join("\n") + "\n", { mode: 0o600 });
    const result = spawnSync(process.execPath, [script, path], { encoding: "utf8" });
    assert.equal(result.status, 1);
    assert.match(result.stderr, /invalid journal transition/);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
