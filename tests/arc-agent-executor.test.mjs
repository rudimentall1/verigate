import test from "node:test";
import assert from "node:assert/strict";
import { executeAuthorizedArcPayment, ARC_CHAIN_ID } from "../integrations/arc-agent-executor.mjs";

const ISSUER = "0x1111111111111111111111111111111111111111";
const AGENT = "0x2222222222222222222222222222222222222222";
const REGISTRY = "0x3333333333333333333333333333333333333333";
const USDC = "0x3600000000000000000000000000000000000000";
const RECIPIENT = "0x4444444444444444444444444444444444444444";
const AUTHORIZATION = { payload: { authorization_id: "0x" + "aa".repeat(32) }, signature: "signed" };

const registrationTx = {
  chainId: "0x13b2",
  from: ISSUER,
  to: REGISTRY,
  data: "0x1234",
  value: "0x0",
};
const consumeTx = {
  chainId: "0x13b2",
  from: AGENT,
  to: REGISTRY,
  data: "0x5678",
  value: "0x0",
};
const paymentTx = {
  chainId: "0x13b2",
  from: AGENT,
  to: USDC,
  data: "0xa9059cbb" + RECIPIENT.slice(2).padStart(64, "0") + "00000000000000000000000000000000000000000000000000000000000186a0",
  value: "0x0",
};

function transactionResponse(hash) {
  return {
    hash,
    async wait() {
      return { status: 1, transactionHash: hash };
    },
  };
}

function signer(address, hash, sent) {
  return {
    async getAddress() { return address; },
    async sendTransaction(tx) {
      sent.push({ address, tx });
      return transactionResponse(hash);
    },
  };
}

function fixture({ agentAddress = AGENT, chainId = BigInt(ARC_CHAIN_ID) } = {}) {
  const sent = [];
  const issuerSigner = signer(ISSUER, "0x" + "11".repeat(32), sent);
  const agentSigner = signer(agentAddress, "0x" + "22".repeat(32), sent);
  agentSigner.sendTransaction = async function(tx) {
    sent.push({ address: agentAddress, tx });
    const hash = sent.filter(x => x.address === agentAddress).length === 1
      ? "0x" + "22".repeat(32)
      : "0x" + "33".repeat(32);
    return transactionResponse(hash);
  };
  const calls = [];
  const fetchImpl = async (url, options) => {
    const body = JSON.parse(options.body);
    calls.push({ url, body });
    let payload;
    if (url.endsWith("/authorize")) {
      payload = {
        execution_authorization: AUTHORIZATION,
        arc_authority: { registration_transaction: registrationTx },
      };
    } else if (url.endsWith("/registration/confirm")) {
      payload = { registered: true, consume_transaction: consumeTx };
    } else if (url.endsWith("/consume/confirm")) {
      payload = {
        execute: true,
        wallet_transaction: paymentTx,
        arc_authority_evidence: { chain_id: ARC_CHAIN_ID },
      };
    } else if (url.endsWith("/payment/confirm")) {
      payload = {
        settled: true,
        payment_settlement: {
          verified: true,
          payment_transaction_hash: "0x" + "33".repeat(32),
        },
      };
    } else {
      throw new Error("unexpected API route " + url);
    }
    return { ok: true, status: 200, async json() { return payload; } };
  };
  return {
    provider: { async getNetwork() { return { chainId }; } },
    issuerSigner,
    agentSigner,
    sent,
    calls,
    fetchImpl,
  };
}

test("headless agent flow separates issuer registration from agent consumption and payment", async () => {
  const f = fixture();
  const result = await executeAuthorizedArcPayment({
    provider: f.provider,
    issuerSigner: f.issuerSigner,
    agentSigner: f.agentSigner,
    apiBaseUrl: "https://verigate.example/",
    authorizationRequest: { identity_id: "id", capability_id: "cap", agent_id: "agent" },
    fetchImpl: f.fetchImpl,
  });

  assert.equal(result.settled, true);
  assert.equal(result.issuer, ISSUER.toLowerCase());
  assert.equal(result.executor, AGENT.toLowerCase());
  assert.equal(result.registration_tx_hash, "0x" + "11".repeat(32));
  assert.equal(result.consume_tx_hash, "0x" + "22".repeat(32));
  assert.equal(result.payment_tx_hash, "0x" + "33".repeat(32));
  assert.deepEqual(f.sent.map(x => x.address), [ISSUER, AGENT, AGENT]);
  assert.equal(f.calls.length, 4);
  assert.equal(f.calls[3].body.payment_tx_hash, result.payment_tx_hash);
});

test("rejects a payment signer that does not match the signed agent executor", async () => {
  const f = fixture({ agentAddress: RECIPIENT });
  await assert.rejects(
    executeAuthorizedArcPayment({
      provider: f.provider,
      issuerSigner: f.issuerSigner,
      agentSigner: f.agentSigner,
      apiBaseUrl: "https://verigate.example",
      authorizationRequest: {},
      fetchImpl: f.fetchImpl,
    }),
    /agent executor Registry consumption signer does not match transaction from address/,
  );
  assert.equal(f.sent.length, 1);
  assert.equal(f.sent[0].address, ISSUER);
  assert.equal(f.calls.some(x => x.url.endsWith("/consume/confirm")), false);
});

test("rejects a non-Arc JSON-RPC provider before making API calls or broadcasting", async () => {
  const f = fixture({ chainId: 1n });
  await assert.rejects(
    executeAuthorizedArcPayment({
      provider: f.provider,
      issuerSigner: f.issuerSigner,
      agentSigner: f.agentSigner,
      apiBaseUrl: "https://verigate.example",
      authorizationRequest: {},
      fetchImpl: f.fetchImpl,
    }),
    /Arc Mainnet/,
  );
  assert.equal(f.sent.length, 0);
  assert.equal(f.calls.length, 0);
});

test("fails closed if the settlement endpoint does not return verified settlement", async () => {
  const f = fixture();
  const originalFetch = f.fetchImpl;
  f.fetchImpl = async (url, options) => {
    if (url.endsWith("/payment/confirm")) {
      f.calls.push({ url, body: JSON.parse(options.body) });
      return { ok: true, status: 200, async json() { return { settled: false, reason: "unfinalized" }; } };
    }
    return originalFetch(url, options);
  };
  await assert.rejects(
    executeAuthorizedArcPayment({
      provider: f.provider,
      issuerSigner: f.issuerSigner,
      agentSigner: f.agentSigner,
      apiBaseUrl: "https://verigate.example",
      authorizationRequest: {},
      fetchImpl: f.fetchImpl,
    }),
    /unfinalized/,
  );
  assert.equal(f.sent.length, 3);
});
