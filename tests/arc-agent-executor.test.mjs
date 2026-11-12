import test from "node:test";
import assert from "node:assert/strict";
import { createHash, generateKeyPairSync, sign } from "node:crypto";
import { executeAuthorizedArcPayment, executeAuthorizedArcPaymentWithSignerClients, ARC_CHAIN_ID } from "../integrations/arc-agent-executor.mjs";

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
  agentAddress = AGENT, signedSender = AGENT, issuerAddress = ISSUER, tokenAddress = USDC, calldataRecipient = RECIPIENT, calldataAmount = 100000, chainId = BigInt(ARC_CHAIN_ID),
  mutate = () => {}, invalidSignature = false, settlement = true, expired = false,
} = {}) {
  const keys = generateKeyPairSync("ed25519");
  const issuedAt = Math.floor(Date.now() / 1000) - 10;
  const expiresAt = expired ? issuedAt + 9 : issuedAt + 240;
  const authorization = {
    algorithm: "Ed25519",
    payload: {
      authorization_version: 1,
      authorization_id: "aa".repeat(32),
      issued_at: issuedAt,
      expires_at: expiresAt,
      action: {
        network: "arc",
        asset: "USDC",
        action_type: "payment",
        target: RECIPIENT,
        amount_exact: "0.1",
        metadata: {
          arc: { chain_id: ARC_CHAIN_ID, asset: "USDC", token_address: tokenAddress, token_decimals: 6 },
          evm_transaction: {
            chain_id: ARC_CHAIN_ID,
            from: signedSender,
            to: tokenAddress,
            data: "0xa9059cbb" + calldataRecipient.slice(2).padStart(64, "0") + WORD(calldataAmount),
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

  const intentHash = createHash("sha256").update(
    `verigate.arc.authority.registry:v2:${ARC_CHAIN_ID}:${REGISTRY.toLowerCase()}:${authorization.algorithm}:${authorization.signature}`,
    "ascii",
  ).digest("hex");
  const registrationTx = {
    chainId: "0x13b2", from: issuerAddress, to: REGISTRY,
    data: "0xb267748a" + authorization.payload.authorization_id + intentHash
      + signedSender.slice(2).toLowerCase().padStart(64, "0") + WORD(expiresAt),
    value: "0x0",
  };
  const consumeTx = {
    chainId: "0x13b2", from: signedSender, to: REGISTRY,
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
    const body = JSON.parse(options.body);
    calls.push({ url, body });
    let payload;
    if (url.endsWith("/authorize")) {
      payload = {
        execution_authorization: responseData.authorization,
        arc_authority: {
          contract_address: REGISTRY,
          issuer: issuerAddress,
          executor: signedSender,
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
    verigatePublicKey: keys.publicKey.export({ type: "spki", format: "pem" }).toString(),
    issuerSigner, agentSigner, sent, calls, fetchImpl,
  };
}

async function run(f, { pinnedRegistry = REGISTRY } = {}) {
  return executeAuthorizedArcPayment({
    provider: f.provider, issuerSigner: f.issuerSigner, agentSigner: f.agentSigner,
    apiBaseUrl: "https://verigate.example/", authorizationRequest: { signed: true },
    verigatePublicKey: f.verigatePublicKey, registryAddress: pinnedRegistry, fetchImpl: f.fetchImpl,
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

test("rejects an expired but correctly signed authorization before broadcast", async () => {
  const f = fixture({ expired: true });
  await assert.rejects(run(f), /expired or has an invalid lifetime/);
  assert.equal(f.sent.length, 0);
});

test("rejects invalid Verigate signature before any transaction broadcast", async () => {
  const f = fixture({ invalidSignature: true });
  await assert.rejects(run(f), /signature is invalid/);
  assert.equal(f.sent.length, 0);
});

test("rejects a Verigate Registry address that differs from the agent's pinned Registry", async () => {
  const f = fixture();
  await assert.rejects(run(f, { pinnedRegistry: RECIPIENT }), /does not match the pinned Registry/);
  assert.equal(f.sent.length, 0);
});

test("rejects signed ERC-20 calldata inconsistent with authorized recipient and amount", async () => {
  const f = fixture({ calldataAmount: 100001 });
  await assert.rejects(run(f), /calldata does not match the signed recipient and amount/);
  assert.equal(f.sent.length, 0);
});

test("rejects a signed payment that substitutes a non-canonical USDC token", async () => {
  const f = fixture({ tokenAddress: RECIPIENT });
  await assert.rejects(run(f), /not canonical Arc USDC/);
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

test("rejects an agent signer that does not match the signed agent sender", async () => {
  const f = fixture({ agentAddress: RECIPIENT, signedSender: AGENT });
  await assert.rejects(run(f), /signed Registry executor does not match agent signer/);
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


async function runViaSignerClients(f, { issuer = ISSUER, agent = AGENT } = {}) {
  const signerCalls = [];
  const issuerSignerClient = {
    async register(authorization) {
      signerCalls.push({ role: "issuer", operation: "register", authorization });
      return { replay: false, result: { txHash: HASH("1"), actualNativeCost: "100" } };
    },
  };
  const agentSignerClient = {
    async consume(authorization) {
      signerCalls.push({ role: "agent", operation: "consume", authorization });
      return { replay: false, result: { txHash: HASH("2"), actualNativeCost: "100" } };
    },
    async payment(authorization) {
      signerCalls.push({ role: "agent", operation: "payment", authorization });
      return { replay: false, result: { txHash: HASH("3"), actualNativeCost: "100" } };
    },
  };
  const result = await executeAuthorizedArcPaymentWithSignerClients({
    issuerSignerClient, agentSignerClient,
    apiBaseUrl: "https://verigate.example/",
    authorizationRequest: { signed: true },
    verigatePublicKey: f.verigatePublicKey,
    registryAddress: REGISTRY,
    issuerAddress: issuer,
    agentAddress: agent,
    fetchImpl: f.fetchImpl,
  });
  return { result, signerCalls };
}

test("executes the Verigate Arc confirmation sequence through typed signer clients without EVM Wallets", async () => {
  const f = fixture();
  const { result, signerCalls } = await runViaSignerClients(f);
  assert.equal(result.settled, true);
  assert.equal(result.issuer, ISSUER.toLowerCase());
  assert.equal(result.executor, AGENT.toLowerCase());
  assert.deepEqual(signerCalls.map(x => [x.role, x.operation]), [
    ["issuer", "register"], ["agent", "consume"], ["agent", "payment"],
  ]);
  assert.equal(f.sent.length, 0);
  assert.equal(f.calls.length, 4);
});

test("socket orchestration rejects issuer or agent pin mismatch before signer requests", async () => {
  const f = fixture();
  const signerCalls = [];
  const issuerSignerClient = { async register() { signerCalls.push("register"); return { result: { txHash: HASH("1") } }; } };
  const agentSignerClient = {
    async consume() { signerCalls.push("consume"); return { result: { txHash: HASH("2") } }; },
    async payment() { signerCalls.push("payment"); return { result: { txHash: HASH("3") } }; },
  };
  await assert.rejects(executeAuthorizedArcPaymentWithSignerClients({
    issuerSignerClient, agentSignerClient,
    apiBaseUrl: "https://verigate.example/",
    authorizationRequest: { signed: true },
    verigatePublicKey: f.verigatePublicKey,
    registryAddress: REGISTRY,
    issuerAddress: RECIPIENT,
    agentAddress: AGENT,
    fetchImpl: f.fetchImpl,
  }), /Verigate issuer does not match the pinned issuer/);
  assert.deepEqual(signerCalls, []);
  assert.equal(f.calls.length, 1);
});
