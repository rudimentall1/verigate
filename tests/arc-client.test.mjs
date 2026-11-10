import test from "node:test";
import assert from "node:assert/strict";
import {
  authorizeArcPayment,
  broadcastAuthorizedArcPayment,
  ARC_CHAIN_HEX,
} from "../integrations/arc-client.mjs";

const executor = "0x1111111111111111111111111111111111111111";
const payer = "0x4444444444444444444444444444444444444444";
const authorization = { payload: { authorization_id: "0xabc" }, signature: "signed" };
const registrationTx = { chainId: ARC_CHAIN_HEX, from: executor, to: "0x222", data: "0xaaaa", value: "0x0" };
const consumeTx = { ...registrationTx, data: "0xbbbb" };
const paymentTx = { ...registrationTx, from: payer, to: "0x333", data: "0xcccc" };

function fixture({ execute = true } = {}) {
  const calls = [];
  let requestCount = 0;
  const provider = {
    async request(args) {
      calls.push({ provider: args });
      if (args.method === "eth_chainId") return ARC_CHAIN_HEX;
      if (args.method === "eth_accounts") return [executor, payer];
      if (args.method === "eth_sendTransaction") return ["0xreg", "0xconsume", "0xpayment"][requestCount++];
      if (args.method === "eth_getTransactionReceipt") return { status: "0x1" };
      throw new Error("unexpected provider method " + args.method);
    },
  };
  const fetchImpl = async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    let payload;
    if (url.endsWith("/authorize")) {
      payload = { execution_authorization: authorization, arc_authority: { registration_transaction: registrationTx } };
    } else if (url.endsWith("/registration/confirm")) {
      payload = { registered: true, consume_transaction: consumeTx };
    } else {
      payload = {
        execute,
        reason: execute ? "ok" : "denied",
        wallet_transaction: execute ? paymentTx : null,
        arc_authority_evidence: { chain_id: 5042 },
      };
    }
    return { ok: true, status: 200, async json() { return payload; } };
  };
  return { provider, fetchImpl, calls };
}

test("Arc authority workflow registers, consumes, and returns payment without broadcasting it", async () => {
  const f = fixture();
  const result = await authorizeArcPayment({
    provider: f.provider,
    apiBaseUrl: "https://verigate.example/",
    authorizationRequest: { identity_id: "id", capability_id: "cap", agent_id: "agent" },
    fetchImpl: f.fetchImpl,
    receiptWait: { timeoutMs: 50, pollIntervalMs: 1 },
  });
  assert.equal(result.registration_tx_hash, "0xreg");
  assert.equal(result.consume_tx_hash, "0xconsume");
  assert.equal(result.wallet_transaction, paymentTx);
  assert.equal(result.payment_broadcast_required, true);
  assert.equal(f.calls.filter(x => x.provider?.method === "eth_sendTransaction").length, 2);
  assert.equal(f.calls.filter(x => x.url?.endsWith("/consume/confirm")).length, 1);
});

test("payment broadcast is a separate explicit wallet operation", async () => {
  const f = fixture();
  const hash = await broadcastAuthorizedArcPayment({ provider: f.provider, walletTransaction: paymentTx });
  assert.equal(hash, "0xreg");
  assert.equal(f.calls.filter(x => x.provider?.method === "eth_sendTransaction").length, 1);
});

test("refuses a wallet connected to a different chain before API or signing calls", async () => {
  const f = fixture();
  f.provider.request = async args => {
    f.calls.push({ provider: args });
    if (args.method === "eth_chainId") return "0x1";
    throw new Error("must not continue");
  };
  await assert.rejects(
    authorizeArcPayment({
      provider: f.provider,
      apiBaseUrl: "https://verigate.example",
      authorizationRequest: {},
      fetchImpl: f.fetchImpl,
    }),
    /Arc Mainnet/,
  );
  assert.equal(f.calls.some(x => x.url), false);
});

test("refuses to sign registry transactions from a wallet other than the configured executor", async () => {
  const f = fixture();
  f.provider.request = async args => {
    f.calls.push({ provider: args });
    if (args.method === "eth_chainId") return ARC_CHAIN_HEX;
    if (args.method === "eth_accounts") return ["0x9999999999999999999999999999999999999999"];
    throw new Error("must not continue");
  };
  await assert.rejects(
    authorizeArcPayment({
      provider: f.provider,
      apiBaseUrl: "https://verigate.example",
      authorizationRequest: {},
      fetchImpl: f.fetchImpl,
    }),
    /wallet that owns this transaction's from address/,
  );
  assert.equal(f.calls.some(x => x.provider?.method === "eth_sendTransaction"), false);
});

test("fails closed when Verigate rejects the on-chain consumption", async () => {
  const f = fixture({ execute: false });
  await assert.rejects(
    authorizeArcPayment({
      provider: f.provider,
      apiBaseUrl: "https://verigate.example",
      authorizationRequest: {},
      fetchImpl: f.fetchImpl,
      receiptWait: { timeoutMs: 50, pollIntervalMs: 1 },
    }),
    /denied/,
  );
  assert.equal(f.calls.filter(x => x.provider?.method === "eth_sendTransaction").length, 2);
});

test("rejects mined registry transactions with failed receipts before calling confirmation", async () => {
  const f = fixture();
  f.provider.request = async args => {
    f.calls.push({ provider: args });
    if (args.method === "eth_chainId") return ARC_CHAIN_HEX;
    if (args.method === "eth_accounts") return [executor];
    if (args.method === "eth_sendTransaction") return "0xreverted";
    if (args.method === "eth_getTransactionReceipt") return { status: "0x0" };
    throw new Error("unexpected provider method " + args.method);
  };
  await assert.rejects(
    authorizeArcPayment({
      provider: f.provider,
      apiBaseUrl: "https://verigate.example",
      authorizationRequest: {},
      fetchImpl: f.fetchImpl,
      receiptWait: { timeoutMs: 50, pollIntervalMs: 1 },
    }),
    /transaction was mined but reverted/,
  );
  assert.equal(f.calls.some(x => x.url?.endsWith("/registration/confirm")), false);
});
