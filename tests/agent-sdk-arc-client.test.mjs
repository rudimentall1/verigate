import test from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  authorizeArcPayment,
  broadcastAuthorizedArcPayment,
  ARC_CHAIN_HEX,
} from "../integrations/arc-client.mjs";

const executor = "0x3333333333333333333333333333333333333333";
const payer = "0x1111111111111111111111111111111111111111";
const recipient = "0x2222222222222222222222222222222222222222";

function buildRequestWithPythonAgentSdk() {
  const source = [
    "import json, tempfile, time",
    "from pathlib import Path",
    "from integrations.agent_sdk import load_or_create_agent_key, public_identity, build_arc_payment_authorization_request",
    "with tempfile.TemporaryDirectory() as td:",
    " key = load_or_create_agent_key(Path(td) / 'agent.key')",
    " identity = public_identity(key, 'cross-language-agent')",
    " request = build_arc_payment_authorization_request(key, agent_id=identity['agent_id'], identity_id=identity['identity_id'], capability_id='cross-language-arc-cap', sender=" + JSON.stringify(payer) + ", recipient=" + JSON.stringify(recipient) + ", amount_usdc='1.250000', resource='cross-language-test', intent_id='cross-language-arc-intent', timestamp=time.time())",
    " print(json.dumps(request))",
  ].join("\n");
  const result = spawnSync("python3", ["-c", source], {
    cwd: process.cwd(),
    encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr || "Python Agent SDK process failed");
  return JSON.parse(result.stdout.trim());
}

test("Python Agent SDK request is accepted by JS Arc wallet client and payment stays explicit", async () => {
  const authorizationRequest = buildRequestWithPythonAgentSdk();
  const signedEvmTx = authorizationRequest.metadata.evm_transaction;
  assert.equal(authorizationRequest.network, "arc");
  assert.equal(authorizationRequest.asset, "USDC");
  assert.equal(authorizationRequest.action_type, "payment");
  assert.equal(typeof authorizationRequest.agent_signature, "string");
  assert.ok(authorizationRequest.agent_signature.length > 20);
  assert.equal(signedEvmTx.chain_id, 5042);
  assert.equal(signedEvmTx.from, payer);

  const expectedPayment = {
    chainId: ARC_CHAIN_HEX,
    from: signedEvmTx.from,
    to: signedEvmTx.to,
    data: signedEvmTx.data,
    value: "0x0",
  };
  const registrationTx = {
    chainId: ARC_CHAIN_HEX,
    from: executor,
    to: "0x4444444444444444444444444444444444444444",
    data: "0x1234",
    value: "0x0",
  };
  const consumeTx = { ...registrationTx, data: "0x5678" };
  const calls = [];
  let sendCount = 0;
  const provider = {
    async request(args) {
      calls.push({ provider: args });
      if (args.method === "eth_chainId") return ARC_CHAIN_HEX;
      if (args.method === "eth_accounts") return [executor, payer];
      if (args.method === "eth_sendTransaction") {
        return ["0xregistration", "0xconsumption", "0xpayment"][sendCount++];
      }
      if (args.method === "eth_getTransactionReceipt") return { status: "0x1" };
      throw new Error("unexpected wallet method: " + args.method);
    },
  };
  const fetchImpl = async (url, options) => {
    const body = JSON.parse(options.body);
    calls.push({ url, body });
    let payload;
    if (url.endsWith("/authorize")) {
      payload = {
        execution_authorization: { payload: { authorization_id: "0xabc" }, signature: "issuer-signature" },
        arc_authority: { registration_transaction: registrationTx },
      };
    } else if (url.endsWith("/registration/confirm")) {
      payload = { registered: true, consume_transaction: consumeTx };
    } else {
      payload = {
        execute: true,
        reason: "consumed",
        wallet_transaction: expectedPayment,
        arc_authority_evidence: { chain_id: 5042 },
      };
    }
    return { ok: true, status: 200, async json() { return payload; } };
  };

  const result = await authorizeArcPayment({
    provider,
    apiBaseUrl: "https://verigate.example",
    authorizationRequest,
    fetchImpl,
    receiptWait: { timeoutMs: 100, pollIntervalMs: 1 },
  });

  const postedRequest = calls.find(call => call.url?.endsWith("/authorize"));
  assert.deepEqual(postedRequest.body, authorizationRequest);
  assert.equal(result.wallet_transaction.to, signedEvmTx.to);
  assert.equal(result.wallet_transaction.data, signedEvmTx.data);
  assert.equal(result.wallet_transaction.from, payer);
  assert.equal(result.payment_broadcast_required, true);
  assert.equal(calls.filter(call => call.provider?.method === "eth_sendTransaction").length, 2);

  const paymentHash = await broadcastAuthorizedArcPayment({
    provider,
    walletTransaction: result.wallet_transaction,
  });
  assert.equal(paymentHash, "0xpayment");
  assert.equal(calls.filter(call => call.provider?.method === "eth_sendTransaction").length, 3);
  const paymentCall = calls.filter(call => call.provider?.method === "eth_sendTransaction")[2];
  assert.deepEqual(paymentCall.provider.params[0], {
    from: expectedPayment.from,
    to: expectedPayment.to,
    data: expectedPayment.data,
    value: expectedPayment.value,
  });
});
