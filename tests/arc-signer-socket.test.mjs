import test from "node:test";
import assert from "node:assert/strict";
import { createConnection } from "node:net";
import { mkdtempSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { generateKeyPairSync, sign } from "node:crypto";
import { createArcSignerSocketServer } from "../integrations/arc-signer-socket.mjs";
import { ARC_CHAIN_ID, ARC_USDC, canonicalJson, OperationJournal } from "../integrations/arc-constrained-signer.mjs";

const AGENT = "0x2222222222222222222222222222222222222222";
const REGISTRY = "0x3333333333333333333333333333333333333333";
const RECIPIENT = "0x4444444444444444444444444444444444444444";
const word = n => BigInt(n).toString(16).padStart(64, "0");

function fixture() {
  const keys = generateKeyPairSync("ed25519");
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    authorization_version: 1,
    authorization_id: "0x" + "ab".repeat(32),
    issued_at: now - 2,
    expires_at: now + 180,
    action: {
      network: "arc", asset: "USDC", action_type: "payment",
      target: RECIPIENT, amount_exact: "1.25",
      metadata: {
        arc: { chain_id: ARC_CHAIN_ID, asset: "USDC", token_address: ARC_USDC, token_decimals: 6 },
        evm_transaction: {
          chain_id: ARC_CHAIN_ID, from: AGENT, to: ARC_USDC,
          data: "0xa9059cbb" + RECIPIENT.slice(2).padStart(64, "0") + word(1250000),
          value_wei: "0",
        },
      },
    },
  };
  return {
    authorization: { algorithm: "Ed25519", payload, signature: sign(null, Buffer.from(canonicalJson(payload)), keys.privateKey).toString("base64") },
    publicKeyPem: keys.publicKey.export({ type: "spki", format: "pem" }).toString(),
  };
}

function request(socketPath, body) {
  return new Promise((resolve, reject) => {
    const socket = createConnection(socketPath);
    let data = "";
    socket.setTimeout(3000, () => socket.destroy(new Error("socket test timeout")));
    socket.on("connect", () => socket.end(JSON.stringify(body) + "\n"));
    socket.on("data", chunk => { data += chunk.toString("utf8"); });
    socket.on("end", () => {
      try { resolve(JSON.parse(data.trim())); } catch (error) { reject(error); }
    });
    socket.on("error", reject);
  });
}

test("Unix socket exposes typed operations, enforces role and returns idempotent result", async () => {
  const dir = mkdtempSync(join(tmpdir(), "verigate-signer-socket-"));
  const socketPath = join(dir, "agent.sock");
  const journal = new OperationJournal(join(dir, "journal.jsonl"));
  const f = fixture();
  let broadcasts = 0;
  const service = createArcSignerSocketServer({
    socketPath, role: "agent", authorizationPublicKeyPem: f.publicKeyPem,
    registryAddress: REGISTRY, signerAddress: AGENT, issuerAddress: "0x1111111111111111111111111111111111111111",
    journal, feePolicy: { maxNativeCost: "100", dailyNativeBudget: "1000" },
    executeOperation: async ({ transaction, onBroadcast }) => {
      broadcasts++;
      if (transaction.operation === "consume") assert.equal(transaction.to, REGISTRY);
      else {
        assert.equal(transaction.operation, "payment");
        assert.equal(transaction.to, ARC_USDC);
      }
      const txHash = transaction.operation === "consume" ? "0x" + "ce".repeat(32) : "0x" + "cd".repeat(32);
      await onBroadcast(txHash);
      return { txHash, actualNativeCost: "50" };
    },
  });
  try {
    await service.listen();
    assert.equal(statSync(socketPath).mode & 0o777, 0o660);
    const premature = await request(socketPath, { operation: "payment", authorization: f.authorization });
    assert.equal(premature.ok, false);
    assert.match(premature.error, /completed consume operation/);
    assert.equal(broadcasts, 0);
    const consumed = await request(socketPath, { operation: "consume", authorization: f.authorization });
    assert.equal(consumed.ok, true);
    assert.equal(consumed.replay, false);
    const first = await request(socketPath, { operation: "payment", authorization: f.authorization });
    assert.equal(first.ok, true);
    assert.equal(first.replay, false);
    const replay = await request(socketPath, { operation: "payment", authorization: f.authorization });
    assert.equal(replay.ok, true);
    assert.equal(replay.replay, true);
    assert.equal(broadcasts, 2);
    const forbidden = await request(socketPath, { operation: "register", authorization: f.authorization });
    assert.equal(forbidden.ok, false);
    assert.match(forbidden.error, /agent signer cannot register/);
    const arbitrary = await request(socketPath, { operation: "payment", authorization: f.authorization, to: RECIPIENT, data: "0xdeadbeef" });
    assert.equal(arbitrary.ok, false);
    assert.match(arbitrary.error, /only operation and authorization/);
    assert.equal(broadcasts, 2);
  } finally {
    await service.close();
    rmSync(dir, { recursive: true, force: true });
  }
});

test("Unix socket refuses to replace an existing path", async () => {
  const dir = mkdtempSync(join(tmpdir(), "verigate-signer-socket-existing-"));
  const socketPath = join(dir, "existing.sock");
  const f = fixture();
  const { writeFileSync } = await import("node:fs");
  writeFileSync(socketPath, "do not replace");
  const service = createArcSignerSocketServer({
    socketPath, role: "agent", authorizationPublicKeyPem: f.publicKeyPem,
    registryAddress: REGISTRY, signerAddress: AGENT, issuerAddress: AGENT,
    journal: new OperationJournal(join(dir, "journal.jsonl")),
    feePolicy: { maxNativeCost: "100", dailyNativeBudget: "1000" },
    executeOperation: async () => { throw new Error("must not execute"); },
  });
  try {
    await assert.rejects(service.listen(), /already exists/);
  } finally {
    await service.close().catch(() => {});
    rmSync(dir, { recursive: true, force: true });
  }
});
