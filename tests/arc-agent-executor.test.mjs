import test from "node:test";
import assert from "node:assert/strict";
import { createHash, generateKeyPairSync, sign } from "node:crypto";
import { executeAuthorizedArcPayment, ARC_CHAIN_ID } from "../integrations/arc-agent-executor.mjs";

const ISSUER = "0x1111111111111111111111111111111111111111";
const AGENT = "0x2222222222222222222222222222222222222222";
const REGISTRY = "0x3333333333333333333333333333333333333333";
const USDC = "0x3600000000000000000000000000000000000000";
const RECIPIENT = "0x4444444444444444444444444444444444444444";
const HASH = (byte) => "0x" + byte.repeat(64);
const WORD = (n) => BigInt(n).toString(16).padStart(64, "0");
const canonicalJson = (value) => {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonicalJson(value[k])}`).join(",")}}`;
  return JSON.stringify(value);
};

function transactionResponse(hash) {
  return { hash, async wait() { return { status: 1, transactionHash: hash }; } };
}
function signer(address, sent, hashes) {
  return {
    async getAddress() { return address; },
    async sendTransaction(tx) {
      sent.push({ address, tx });
      return transactionResponse(hashes[sent.filter(x => x.address === address).length - 1]);
    },
  };
}

function fixture({
  agentAddress = AGENT, issuerAddress = ISSUER, chainId = BigInt(ARC_CHAIN_ID),
  mutate = () => {}, invalidSignature = false, settlement = true,
} = {}) {
  const keys = generateKeyPairSync("ed25519");
  const expiresAt = 1900000000;
  const authorization = {
    algorithm: "Ed25519",
    payload: {
      authorization_version: 1,
      authorization_id: "aa".repeat(32),
      expires_at: expiresAt,
      action: {
        network: "arc",
        asset: "USDC",
        action_type: "payment",
        target: RECIPIENT,
        amount_exact: "0.1",
        metadata: {
          evm_transaction: {
            chain_id: ARC_CHAIN_ID,
            from: agentAddress,
            to: USDC,
            data: "0xa9059cbb" + RECIPIENT.slice(2).padStart(64, "0") + WORD(100000),
            value_wei: "0",
          },
        },
      },
    },
  };
  authorization.signature = sign(
    null, Buffer.from(canonicalJson(authorization.payload)), keys.privateKey,
  ).toString("base64");
  if (invalidSignature) authorization.signature = Buffer.alloc(64, 7).toString("base64");

  const intentHash = createHash("sha256").update(canonicalJson({
    domain: "verigate.arc.authority.registry",
    version: 1,
    chain_id: ARC_CHAIN_ID,
    contract: REGISTRY.toLowerCase(),
    authorization,
  })).digest("hex");
  const registrationTx = {
    chainId: "0x13b2", from: issuerAddress, to: REGISTRY,
    data: "0xb267748a" + authorization.payload.authorization_id + intentHash
      + agentAddress.slice(2).toLowerCase().padStart(64, "0") + WORD(expiresAt),
    value: "0x0",
  };
  const consumeTx = {
    chainId: "0x13b2", from: agentAddress, to: REGISTRY,
    data: "0xbad56b75" + authorization.payload.authorization_id + intentHash,
    value: "0x0",
  };
  const paymentTx = {
    chainId: "0x13b2", from: agentAddress, to: USDC,
    data: authorization.payload.action.metadata.evm_transaction.data,
    value: "0x0",
  };
  const responseData = {
    authorization,
    registrationTx: structuredClone(registrationTx),
    consumeTx: structuredClone(consumeTx),
    paymentTx: structuredClone(paymentTx),
  };
  mutate(responseData);

  const sent = [];
  const hashes = [HASH("1"), HASH("2"), HASH("3")];
  const issuerSigner = signer(issuerAddress, sent, hashes);
  const agentSigner = signer(agentAddress, sent, hashes);
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    if (url.endsWith("/v1/public-key")) {
      return { ok: true, status: 200, async text() { return keys.publicKey.export({ type: "spki", format: "pem" }).toString(); } };
    }
    const body = JSON.parse(options.body);
    calls.push({ url, body });
    let payload;
    if (url.endsWith("/authorize")) {
      payload = {
        execution_authorization: responseData.authorization,
        arc_authority: {
          contract_address: REGISTRY,
          issuer: issuerAddress,
          executor: agentAddress,
          registration_transaction: responseData.registrationTx,
        },
      };
    } else if (url.endsWith("/registration/confirm")) {
      payload = { registered: true, consume_transaction: responseData.consumeTx };
    } else if (url.endsWith("/consume/confirm")) {
      payload = {
        execute: true, wallet_transaction: responseData.paymentTx,
        arc_authority_evidence: { chain_id: ARC_CHAIN_ID, executor: agentAddress },
      };
    } else if (url.endsWith("/payment/confirm")) {
      payload = settlement ? {
        settled: true, payment_settlement: { verified: true, payment_transaction_hash: HASH("3") },
      } : { settled: false, reason: "unfinalized" };
    } else {
      throw new Error("unexpected API route " + url);
    }
    return { ok: true, status: 200, async json() { return payload; } };
  };
  return {
    provider: { async getNetwork() { return { chainId }; } },
    issuerSigner, agentSigner, sent, calls, fetchImpl,
  };
}

async function run(f) {
  return executeAuthorizedArcPayment({
    provider: f.provider, issuerSigner: f.issuerSigner, agentSigner: f.agentSigner,
    apiBaseUrl: "https://verigate.example/", authorizationRequest: { signed: true },
    fetchImpl: f.fetchImpl,
  });
}

test("verifies signed authorization and separates issuer registration from agent execution", async () => {
  const f = fixture();
  const result = await run(f);
  assert.equal(result.settled, true);
  assert.equal(result.issuer, ISSUER.toLowerCase());
  assert.equal(result.executor, AGENT.toLowerCase());
  assert.deepEqual(f.sent.map(x => x.address), [ISSUER, AGENT, AGENT]);
  assert.equal(f.calls.length, 4);
});

test("rejects identical issuer and agent signer addresses before API calls", async () => {
  const f = fixture({ issuerAddress: AGENT });
  await assert.rejects(run(f), /must be different addresses/);
  assert.equal(f.sent.length, 0);
  assert.equal(f.calls.length, 0);
});

test("rejects invalid Verigate signature before any transaction broadcast", async () => {
  const f = fixture({ invalidSignature: true });
  await assert.rejects(run(f), /signature is invalid/);
  assert.equal(f.sent.length, 0);
});

test("rejects a registration transaction redirected away from the signed Registry", async () => {
  const f = fixture({ mutate: (d) => { d.registrationTx.to = RECIPIENT; } });
  await assert.rejects(run(f), /destination does not match independently derived destination/);
  assert.equal(f.sent.length, 0);
});

test("rejects substituted Registry registration calldata before issuer signing", async () => {
  const f = fixture({ mutate: (d) => { d.registrationTx.data = "0x12345678"; } });
  await assert.rejects(run(f), /calldata does not match independently derived operation/);
  assert.equal(f.sent.length, 0);
});

test("rejects substituted Registry consumption calldata before agent signing", async () => {
  const f = fixture({ mutate: (d) => { d.consumeTx.data = "0x12345678"; } });
  await assert.rejects(run(f), /calldata does not match independently derived operation/);
  assert.equal(f.sent.length, 1);
  assert.equal(f.sent[0].address, ISSUER);
});

test("rejects payment recipient, token destination or amount substitution before payment signing", async (t) => {
  for (const [label, mutation] of [
    ["recipient", (d) => { d.paymentTx.data = d.paymentTx.data.replace(RECIPIENT.slice(2), "55".repeat(20)); }],
    ["token", (d) => { d.paymentTx.to = RECIPIENT; }],
    ["amount", (d) => { d.paymentTx.data = d.paymentTx.data.slice(0, -1) + "1"; }],
  ]) {
    await t.test(label, async () => {
      const f = fixture({ mutate: mutation });
      await assert.rejects(run(f), /does not match independently derived/);
      assert.equal(f.sent.length, 2);
      assert.deepEqual(f.sent.map(x => x.address), [ISSUER, AGENT]);
    });
  }
});

test("rejects a payment signer that does not match the signed agent sender", async () => {
  const f = fixture({ agentAddress: RECIPIENT });
  await assert.rejects(run(f), /signed payment sender/);
  assert.equal(f.sent.length, 0);
});

test("rejects a non-Arc provider before API calls or broadcasts", async () => {
  const f = fixture({ chainId: 1n });
  await assert.rejects(run(f), /Arc Mainnet/);
  assert.equal(f.sent.length, 0);
  assert.equal(f.calls.length, 0);
});

test("fails closed if settlement is not independently confirmed", async () => {
  const f = fixture({ settlement: false });
  await assert.rejects(run(f), /unfinalized/);
  assert.equal(f.sent.length, 3);
});
