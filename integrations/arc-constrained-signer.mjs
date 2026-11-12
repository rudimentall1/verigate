/**
 * Constrained Arc signer policy core.
 *
 * This module is deliberately not a generic transaction signer. It validates
 * a Verigate Ed25519 authorization, derives the only permitted Arc calldata,
 * enforces role/fee policy and provides a fail-closed durable operation journal.
 * Socket transport and the ethers broadcast adapter are separate layers.
 */
import { createHash, createPublicKey, verify as verifySignature } from "node:crypto";
import { appendFileSync, closeSync, existsSync, fsyncSync, openSync, readFileSync, unlinkSync } from "node:fs";

export const ARC_CHAIN_ID = 5042;
export const ARC_USDC = "0x3600000000000000000000000000000000000000";
export const REGISTER_SELECTOR = "0xb267748a";
export const CONSUME_SELECTOR = "0xbad56b75";
export const TRANSFER_SELECTOR = "0xa9059cbb";
const MAX_AUTH_LIFETIME_SECONDS = 300;

function assert(ok, message) { if (!ok) throw new Error(message); }
export function normalizeAddress(v, name = "address") {
  assert(typeof v === "string" && /^0x[0-9a-fA-F]{40}$/.test(v), name + " must be a 20-byte EVM address");
  return v.toLowerCase();
}
function uintWord(v, name) {
  let n; try { n = BigInt(v); } catch { throw new Error(name + " must be an unsigned integer"); }
  assert(n >= 0n && n < (1n << 256n), name + " is outside uint256");
  return n.toString(16).padStart(64, "0");
}
function addressWord(v, name) { return normalizeAddress(v, name).slice(2).padStart(64, "0"); }
export function canonicalJson(v) {
  if (Array.isArray(v)) return "[" + v.map(canonicalJson).join(",") + "]";
  if (v && typeof v === "object") return "{" + Object.keys(v).sort().map(k => JSON.stringify(k) + ":" + canonicalJson(v[k])).join(",") + "}";
  return JSON.stringify(v);
}
function parseUsdc(value) {
  assert(typeof value === "string" && /^(0|[1-9][0-9]*)(\.[0-9]{1,6})?$/.test(value), "USDC amount must be a canonical decimal with at most 6 places");
  const [whole, fraction = ""] = value.split(".");
  const units = BigInt(whole) * 1000000n + BigInt((fraction + "000000").slice(0, 6));
  assert(units > 0n, "USDC amount must be positive");
  return units;
}

export function verifyExecutionAuthorization(authorization, publicKeyPem, now = Math.floor(Date.now() / 1000)) {
  assert(authorization && authorization.algorithm === "Ed25519", "unsupported or missing authorization algorithm");
  assert(authorization.payload && typeof authorization.payload === "object", "authorization payload missing");
  assert(typeof authorization.signature === "string", "authorization signature missing");
  let signature;
  try { signature = Buffer.from(authorization.signature, "base64"); } catch { throw new Error("malformed authorization signature"); }
  assert(signature.length === 64, "authorization signature must be 64 bytes");
  const key = createPublicKey(publicKeyPem);
  assert(key.asymmetricKeyType === "ed25519", "pinned key must be Ed25519");
  assert(verifySignature(null, Buffer.from(canonicalJson(authorization.payload)), key, signature), "invalid Verigate authorization signature");
  const p = authorization.payload;
  assert(Number.isSafeInteger(p.issued_at) && Number.isSafeInteger(p.expires_at), "authorization timestamps must be integer seconds");
  assert(p.issued_at <= now && p.expires_at > now, "authorization is not currently valid");
  assert(p.expires_at > p.issued_at && p.expires_at - p.issued_at <= MAX_AUTH_LIFETIME_SECONDS, "authorization lifetime exceeds 300 seconds");
  assert(typeof p.authorization_id === "string" && /^0x[0-9a-fA-F]{64}$/.test(p.authorization_id), "authorization_id must be bytes32");
  const action = p.action;
  const evm = action?.metadata?.evm_transaction;
  assert(action?.network === "arc" && action?.asset === "USDC" && action?.action_type === "payment", "authorization is not an Arc USDC payment");
  assert(Number(evm?.chain_id) === ARC_CHAIN_ID, "authorization chain must be Arc Mainnet (5042)");
  assert(normalizeAddress(evm?.to, "USDC token") === ARC_USDC, "authorization does not target canonical Arc USDC");
  assert(Number(action.metadata.arc?.token_decimals) === 6, "Arc USDC decimals must be 6");
  const sender = normalizeAddress(evm.from, "payment sender");
  const recipient = normalizeAddress(action.target, "payment recipient");
  assert(recipient !== "0x0000000000000000000000000000000000000000", "zero recipient is forbidden");
  const amount = parseUsdc(action.amount_exact);
  const expectedTransfer = TRANSFER_SELECTOR + addressWord(recipient, "recipient") + uintWord(amount, "USDC amount");
  assert(typeof evm.data === "string" && evm.data.toLowerCase() === expectedTransfer, "signed calldata does not match recipient and amount");
  assert(BigInt(evm.value_wei ?? "0") === 0n, "native value must be zero");
  return { payload: p, sender, recipient, amount, expectedTransfer };
}

export function deriveArcOperation({ role, operation, authorization, publicKeyPem, registryAddress, signerAddress, issuerAddress, now }) {
  const verified = verifyExecutionAuthorization(authorization, publicKeyPem, now);
  const registry = normalizeAddress(registryAddress, "pinned Registry");
  const signer = normalizeAddress(signerAddress, "signer address");
  const p = verified.payload;
  const intentHash = createHash("sha256").update(
    `verigate.arc.authority.registry:v2:${ARC_CHAIN_ID}:${registry}:${authorization.algorithm}:${authorization.signature}`, "ascii",
  ).digest("hex");
  const id = p.authorization_id.slice(2).toLowerCase();
  if (operation === "register") {
    assert(role === "issuer", "agent signer cannot register authorizations");
    assert(signer === normalizeAddress(issuerAddress, "configured issuer"), "issuer signer address mismatch");
    const data = REGISTER_SELECTOR + id + intentHash + addressWord(verified.sender, "agent sender") + uintWord(p.expires_at, "expiry");
    return { chainId: ARC_CHAIN_ID, to: registry, data, value: 0n, operation, authorizationId: p.authorization_id };
  }
  assert(role === "agent", "issuer signer cannot execute agent operations");
  assert(signer === verified.sender, "agent signer does not match signed sender");
  if (operation === "consume") {
    return { chainId: ARC_CHAIN_ID, to: registry, data: CONSUME_SELECTOR + id + intentHash, value: 0n, operation, authorizationId: p.authorization_id };
  }
  if (operation === "payment") {
    return { chainId: ARC_CHAIN_ID, to: ARC_USDC, data: verified.expectedTransfer, value: 0n, operation, authorizationId: p.authorization_id };
  }
  throw new Error("unsupported signer operation");
}

export function validateFeePolicy({ gasLimit, maxFeePerGas, maxPriorityFeePerGas, maxNativeCost, dailyNativeBudget }, feeData) {
  const fields = { gasLimit, maxFeePerGas, maxPriorityFeePerGas, maxNativeCost, dailyNativeBudget };
  for (const [k, v] of Object.entries(fields)) {
    let n; try { n = BigInt(v); } catch { throw new Error(k + " must be configured as an integer"); }
    assert(n > 0n, k + " must be positive");
    fields[k] = n;
  }
  assert(fields.maxPriorityFeePerGas <= fields.maxFeePerGas, "priority fee cannot exceed max fee");
  assert(fields.gasLimit * fields.maxFeePerGas <= fields.maxNativeCost, "per-operation fee ceiling is inconsistent with gas and max fee");
  assert(feeData && feeData.maxFeePerGas != null && feeData.maxPriorityFeePerGas != null, "live RPC fee data unavailable");
  const liveMax = BigInt(feeData.maxFeePerGas);
  const livePriority = BigInt(feeData.maxPriorityFeePerGas);
  assert(liveMax <= fields.maxFeePerGas, "live max fee exceeds signer policy");
  assert(livePriority <= fields.maxPriorityFeePerGas, "live priority fee exceeds signer policy");
  return fields;
}

/**
 * Append-only journal. An unresolved reservation is intentionally never retried:
 * after a crash, operator reconciliation must determine whether broadcast occurred.
 */
export class OperationJournal {
  constructor(path) { this.path = path; }
  records() {
    if (!existsSync(this.path)) return [];
    return readFileSync(this.path, "utf8").split("\n").filter(Boolean).map(line => JSON.parse(line));
  }
  reserve(authorizationId, operation) {
    const lockPath = this.path + ".lock";
    let lock;
    try { lock = openSync(lockPath, "wx", 0o600); }
    catch { throw new Error("journal is locked; refusing concurrent operation"); }
    try {
      const rows = this.records();
      const prior = rows.filter(x => x.authorizationId === authorizationId && x.operation === operation).at(-1);
      if (prior) {
        if (prior.state === "complete") return { replay: true, result: prior.result };
        throw new Error("operation has an unresolved reservation; operator reconciliation required");
      }
      const fd = openSync(this.path, "a", 0o600);
      try {
        appendFileSync(fd, JSON.stringify({ authorizationId, operation, state: "reserved", at: Date.now() }) + "\n");
        fsyncSync(fd);
      } finally { closeSync(fd); }
      return { replay: false };
    } finally { closeSync(lock); }
  }
  complete(authorizationId, operation, result) {
    const fd = openSync(this.path, "a", 0o600);
    try {
      appendFileSync(fd, JSON.stringify({ authorizationId, operation, state: "complete", result, at: Date.now() }) + "\n");
      fsyncSync(fd);
    } finally { closeSync(fd); }
  }
}
