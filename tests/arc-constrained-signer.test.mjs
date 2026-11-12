import test from "node:test";
import assert from "node:assert/strict";
import { chmodSync, linkSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { generateKeyPairSync, sign } from "node:crypto";
import {
  ARC_CHAIN_ID, ARC_USDC, deriveArcOperation, verifyExecutionAuthorization,
  validateFeePolicy, OperationJournal, canonicalJson,
} from "../integrations/arc-constrained-signer.mjs";

const ISSUER = "0x1111111111111111111111111111111111111111";
const AGENT = "0x2222222222222222222222222222222222222222";
const REGISTRY = "0x3333333333333333333333333333333333333333";
const RECIPIENT = "0x4444444444444444444444444444444444444444";
const word = n => BigInt(n).toString(16).padStart(64, "0");

function authFixture(overrides = {}) {
  const keys = generateKeyPairSync("ed25519");
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    authorization_version: 1,
    authorization_id: "0x" + "aa".repeat(32),
    issued_at: now - 5,
    expires_at: now + 240,
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
    ...overrides,
  };
  const authorization = {
    algorithm: "Ed25519", payload,
    signature: sign(null, Buffer.from(canonicalJson(payload)), keys.privateKey).toString("base64"),
  };
  const pem = keys.publicKey.export({ type: "spki", format: "pem" }).toString();
  return { authorization, pem, publicKeyPem: pem, privateKey: keys.privateKey };
}

test("verifies signed authorization and derives exact USDC transfer", () => {
  const f = authFixture();
  const v = verifyExecutionAuthorization(f.authorization, f.pem);
  assert.equal(v.sender, AGENT);
  assert.equal(v.recipient, RECIPIENT);
  assert.equal(v.amount, 1250000n);
  const tx = deriveArcOperation({ role: "agent", operation: "payment", ...f, registryAddress: REGISTRY, signerAddress: AGENT });
  assert.equal(tx.chainId, ARC_CHAIN_ID);
  assert.equal(tx.to, ARC_USDC);
  assert.equal(tx.data, f.authorization.payload.action.metadata.evm_transaction.data);
  assert.equal(tx.value, 0n);
});

test("issuer can derive registration but cannot consume", () => {
  const f = authFixture();
  const tx = deriveArcOperation({ role: "issuer", operation: "register", ...f, registryAddress: REGISTRY, signerAddress: ISSUER, issuerAddress: ISSUER });
  assert.equal(tx.to, REGISTRY);
  assert.equal(tx.data.slice(0, 10), "0xb267748a");
  assert.throws(() => deriveArcOperation({ role: "issuer", operation: "consume", ...f, registryAddress: REGISTRY, signerAddress: ISSUER, issuerAddress: ISSUER }), /issuer signer cannot execute/);
});

test("agent cannot register and wrong sender cannot execute", () => {
  const f = authFixture();
  assert.throws(() => deriveArcOperation({ role: "agent", operation: "register", ...f, registryAddress: REGISTRY, signerAddress: AGENT }), /agent signer cannot register/);
  assert.throws(() => deriveArcOperation({ role: "agent", operation: "payment", ...f, registryAddress: REGISTRY, signerAddress: ISSUER }), /does not match signed sender/);
});

test("rejects tampered payload, wrong chain, noncanonical token and expired authorization", () => {
  const f = authFixture();
  const tampered = structuredClone(f.authorization);
  tampered.payload.action.amount_exact = "99";
  assert.throws(() => verifyExecutionAuthorization(tampered, f.pem), /invalid Verigate authorization signature/);
  const expired = authFixture({ issued_at: Math.floor(Date.now() / 1000) - 500, expires_at: Math.floor(Date.now() / 1000) - 1 });
  assert.throws(() => verifyExecutionAuthorization(expired.authorization, expired.pem), /not currently valid/);
  const wrongChain = authFixture();
  wrongChain.authorization.payload.action.metadata.evm_transaction.chain_id = 1;
  wrongChain.authorization.signature = sign(null, Buffer.from(canonicalJson(wrongChain.authorization.payload)), generateKeyPairSync("ed25519").privateKey).toString("base64");
  assert.throws(() => verifyExecutionAuthorization(wrongChain.authorization, wrongChain.pem), /invalid Verigate authorization signature/);
});

test("rejects inconsistent fee configuration and live fee spikes", () => {
  const policy = { gasLimit: "100000", maxFeePerGas: "100", maxPriorityFeePerGas: "5", maxNativeCost: "10000000", dailyNativeBudget: "50000000" };
  assert.equal(validateFeePolicy(policy, { maxFeePerGas: 90n, maxPriorityFeePerGas: 2n }).gasLimit, 100000n);
  assert.throws(() => validateFeePolicy(policy, { maxFeePerGas: 101n, maxPriorityFeePerGas: 2n }), /exceeds signer policy/);
  assert.throws(() => validateFeePolicy({ ...policy, maxPriorityFeePerGas: "101" }, { maxFeePerGas: 90n, maxPriorityFeePerGas: 2n }), /priority fee cannot exceed/);
});

test("journal reserves once and returns completed result without a second reservation", () => {
  const dir = mkdtempSync(join(tmpdir(), "verigate-signer-"));
  try {
    const journal = new OperationJournal(join(dir, "ops.jsonl"));
    const id = "0x" + "aa".repeat(32);
    assert.deepEqual(journal.reserve(id, "consume"), { replay: false });
    const txHash = "0x" + "12".repeat(32);
    journal.markBroadcast(id, "consume", txHash);
    assert.throws(() => journal.complete(id, "consume", { txHash: "0x" + "ff".repeat(32) }), /must match the durable broadcast record/);
    journal.complete(id, "consume", { txHash });
    assert.deepEqual(journal.reserve(id, "payment"), { replay: true, result: { txHash } });
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("journal fails closed on unresolved reservation and duplicate completion", () => {
  const dir = mkdtempSync(join(tmpdir(), "verigate-signer-"));
  try {
    const journal = new OperationJournal(join(dir, "ops.jsonl"));
    const id = "0x" + "bb".repeat(32);
    journal.reserve(id, "consume");
    assert.throws(() => journal.reserve(id, "consume"), /operator reconciliation/);
    journal.markBroadcast(id, "consume", "0x" + "45".repeat(32));
    assert.throws(() => journal.reserve(id, "consume"), /operator reconciliation/);
    journal.complete(id, "consume", { txHash: "0x" + "45".repeat(32) });
    assert.throws(() => journal.complete(id, "consume", { txHash: "0x" + "78".repeat(32) }), /durably recorded broadcast/);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("rejects Arc metadata that conflicts with the pinned chain or token", () => {
  const wrongChain = authFixture();
  wrongChain.authorization.payload.action.metadata.arc.chain_id = 1;
  wrongChain.authorization.signature = sign(null, Buffer.from(canonicalJson(wrongChain.authorization.payload)), wrongChain.privateKey).toString("base64");
  assert.throws(() => verifyExecutionAuthorization(wrongChain.authorization, wrongChain.pem), /Arc metadata chain/);
  const wrongToken = authFixture();
  wrongToken.authorization.payload.action.metadata.arc.token_address = AGENT;
  wrongToken.authorization.signature = sign(null, Buffer.from(canonicalJson(wrongToken.authorization.payload)), wrongToken.privateKey).toString("base64");
  assert.throws(() => verifyExecutionAuthorization(wrongToken.authorization, wrongToken.pem), /Arc metadata token/);
});

test("journal enforces cumulative daily native-token budget across reservations and completions", () => {
  const dir = mkdtempSync(join(tmpdir(), "verigate-signer-budget-"));
  try {
    const journal = new OperationJournal(join(dir, "ops.jsonl"));
    const day = Date.parse("2026-11-12T10:00:00.000Z");
    journal.reserve("0x" + "01".repeat(32), "register", { maxNativeCost: "40", dailyNativeBudget: "100", now: day });
    journal.markBroadcast("0x" + "01".repeat(32), "register", "0x" + "aa".repeat(32));
    journal.complete("0x" + "01".repeat(32), "register", { txHash: "0x" + "aa".repeat(32) }, "30");
    journal.reserve("0x" + "02".repeat(32), "consume", { maxNativeCost: "60", dailyNativeBudget: "100", now: day + 1000 });
    assert.throws(() => journal.reserve("0x" + "03".repeat(32), "consume", { maxNativeCost: "11", dailyNativeBudget: "100", now: day + 2000 }), /daily native-token budget/);
    journal.markBroadcast("0x" + "02".repeat(32), "consume", "0x" + "bb".repeat(32));
    assert.throws(() => journal.complete("0x" + "02".repeat(32), "consume", { txHash: "0x" + "bb".repeat(32) }, "61"), /exceeds reserved/);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("accepts Verigate authorization IDs encoded as bare bytes32 hex", () => {
  const f = authFixture();
  f.authorization.payload.authorization_id = "cc".repeat(32);
  f.authorization.signature = sign(null, Buffer.from(canonicalJson(f.authorization.payload)), f.privateKey).toString("base64");
  const verified = verifyExecutionAuthorization(f.authorization, f.pem);
  assert.equal(verified.payload.authorization_id, "cc".repeat(32));
  const tx = deriveArcOperation({
    role: "issuer", operation: "register", ...f,
    registryAddress: REGISTRY, signerAddress: ISSUER, issuerAddress: ISSUER,
  });
  assert.equal(tx.data.slice(10, 74), "cc".repeat(32));
});

test("journal rejects symlinks, hard links and group/world-readable files", () => {
  const dir = mkdtempSync(join(tmpdir(), "verigate-signer-journal-security-"));
  try {
    const target = join(dir, "target.jsonl");
    const link = join(dir, "symlink.jsonl");
    writeFileSync(target, "", { mode: 0o600 });
    symlinkSync(target, link);
    assert.throws(() => new OperationJournal(link).records(), /regular file/);

    const hardLinked = join(dir, "hardlinked.jsonl");
    writeFileSync(hardLinked, "", { mode: 0o600 });
    linkSync(hardLinked, join(dir, "hardlink-alias.jsonl"));
    assert.throws(() => new OperationJournal(hardLinked).records(), /additional hard links/);

    const broad = join(dir, "broad.jsonl");
    writeFileSync(broad, "", { mode: 0o600 });
    chmodSync(broad, 0o644);
    assert.throws(() => new OperationJournal(broad).records(), /permissions are too broad/);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("unresolved signer broadcasts remain reserved across UTC midnight", () => {
  const dir = mkdtempSync(join(tmpdir(), "verigate-signer-midnight-budget-"));
  try {
    const journal = new OperationJournal(join(dir, "ops.jsonl"));
    const beforeMidnight = Date.parse("2026-11-11T23:59:00.000Z");
    const afterMidnight = Date.parse("2026-11-12T00:01:00.000Z");
    const firstId = "0x" + "91".repeat(32);
    journal.reserve(firstId, "consume", {
      maxNativeCost: "80", dailyNativeBudget: "100", now: beforeMidnight,
    });
    journal.markBroadcast(firstId, "consume", "0x" + "91".repeat(32));
    assert.throws(() => journal.reserve("0x" + "92".repeat(32), "payment", {
      maxNativeCost: "21", dailyNativeBudget: "100", now: afterMidnight,
    }), /daily native-token budget/);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("journal blocks payment until the same authorization has a completed consume", () => {
  const dir = mkdtempSync(join(tmpdir(), "verigate-signer-consume-gate-"));
  try {
    const journal = new OperationJournal(join(dir, "ops.jsonl"));
    const id = "0x" + "a1".repeat(32);
    assert.throws(() => journal.reserve(id, "payment"), /completed consume operation/);
    assert.deepEqual(journal.reserve(id, "consume"), { replay: false });
    journal.markBroadcast(id, "consume", "0x" + "a2".repeat(32));
    assert.throws(() => journal.reserve(id, "payment"), /completed consume operation/);
    journal.complete(id, "consume", { txHash: "0x" + "a2".repeat(32) });
    assert.deepEqual(journal.reserve(id, "payment"), { replay: false });
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("canonicalizes prefixed and bare authorization IDs to one journal key", () => {
  const f = authFixture();
  const prefixed = deriveArcOperation({
    role: "agent", operation: "consume", ...f,
    registryAddress: REGISTRY, signerAddress: AGENT,
  }).authorizationId;
  const bareAuthorization = structuredClone(f.authorization);
  bareAuthorization.payload.authorization_id = "aa".repeat(32);
  bareAuthorization.signature = sign(
    null, Buffer.from(canonicalJson(bareAuthorization.payload)), f.privateKey,
  ).toString("base64");
  const bare = deriveArcOperation({
    role: "agent", operation: "consume",
    authorization: bareAuthorization, publicKeyPem: f.pem,
    registryAddress: REGISTRY, signerAddress: AGENT,
  }).authorizationId;
  assert.equal(prefixed, "aa".repeat(32));
  assert.equal(bare, prefixed);
});
