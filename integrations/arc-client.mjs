/**
 * Optional EIP-1193 browser adapter for Verigate's Arc Authority Registry flow.
 *
 * This module requires the connected provider to expose both the Registry
 * issuer account and the agent executor account. Autonomous agents should use
 * arc-agent-executor.mjs with separate operator and agent signers instead.
 */

const ARC_CHAIN_ID = 5042;
const ARC_CHAIN_HEX = "0x13b2";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function txForWallet(transaction) {
  assert(transaction && typeof transaction === "object", "wallet transaction is missing");
  const tx = {};
  for (const key of ["from", "to", "data", "value"]) {
    assert(typeof transaction[key] === "string", `wallet transaction ${key} is missing`);
    tx[key] = transaction[key];
  }
  return tx;
}

async function ensureArc(provider) {
  assert(provider && typeof provider.request === "function", "an EIP-1193 wallet provider is required");
  const chainId = await provider.request({ method: "eth_chainId" });
  assert(
    typeof chainId === "string" && BigInt(chainId) === BigInt(ARC_CHAIN_ID),
    `wallet must be connected to Arc Mainnet (chain ID ${ARC_CHAIN_ID})`,
  );
}

async function ensureTransactionAccount(provider, transaction) {
  const expected = transaction?.from;
  assert(typeof expected === "string", "registry transaction executor is missing");
  const accounts = await provider.request({ method: "eth_accounts" });
  assert(Array.isArray(accounts), "wallet did not return its connected accounts");
  assert(
    accounts.some(account => typeof account === "string" && account.toLowerCase() === expected.toLowerCase()),
    `connect the wallet that owns this transaction's from address (${expected}) before continuing`,
  );
}

async function postJson(fetchImpl, url, body, headers) {
  const response = await fetchImpl(url, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`Verigate returned a non-JSON response (HTTP ${response.status})`);
  }
  if (!response.ok) {
    const detail = payload?.detail || payload?.error || `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

async function waitForReceipt(provider, transactionHash, {
  timeoutMs = 120_000,
  pollIntervalMs = 1_000,
} = {}) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const receipt = await provider.request({
      method: "eth_getTransactionReceipt",
      params: [transactionHash],
    });
    if (receipt) {
      assert(
        receipt.status === "0x1" || receipt.status === 1 || receipt.status === "1",
        `Arc transaction was mined but reverted: ${transactionHash}`,
      );
      return receipt;
    }
    await new Promise(resolve => setTimeout(resolve, pollIntervalMs));
  }
  throw new Error(`timed out waiting for Arc transaction receipt: ${transactionHash}`);
}

/**
 * Run registration and consumption, returning the authorized payment tx.
 * authorizationRequest must already contain the signed agent intent fields.
 */
export async function authorizeArcPayment({
  provider,
  apiBaseUrl,
  authorizationRequest,
  fetchImpl = globalThis.fetch,
  headers = {},
  receiptWait = {},
}) {
  assert(typeof apiBaseUrl === "string" && apiBaseUrl.length > 0, "apiBaseUrl is required");
  assert(typeof fetchImpl === "function", "fetch implementation is required");
  assert(authorizationRequest && typeof authorizationRequest === "object", "signed authorization request is required");
  await ensureArc(provider);

  const base = apiBaseUrl.replace(/\/$/, "");
  const authorized = await postJson(
    fetchImpl,
    `${base}/v1/integrations/arc/authorize`,
    authorizationRequest,
    headers,
  );
  const authorization = authorized.execution_authorization;
  const registrationTx = authorized.arc_authority?.registration_transaction;
  assert(authorization && typeof authorization === "object", "Verigate did not return a signed execution authorization");
  assert(registrationTx, "Verigate did not return an Arc registration transaction");

  await ensureTransactionAccount(provider, registrationTx);
  const registrationHash = await provider.request({
    method: "eth_sendTransaction",
    params: [txForWallet(registrationTx)],
  });
  await waitForReceipt(provider, registrationHash, receiptWait);

  const registered = await postJson(
    fetchImpl,
    `${base}/v1/integrations/arc/registration/confirm`,
    { authorization, registration_tx_hash: registrationHash },
    headers,
  );
  assert(registered.registered === true, "Verigate did not confirm Arc registration");
  const consumeTx = registered.consume_transaction;
  assert(consumeTx, "Verigate did not return the Arc consumption transaction");

  await ensureTransactionAccount(provider, consumeTx);
  const consumeHash = await provider.request({
    method: "eth_sendTransaction",
    params: [txForWallet(consumeTx)],
  });
  await waitForReceipt(provider, consumeHash, receiptWait);

  const consumed = await postJson(
    fetchImpl,
    `${base}/v1/integrations/arc/consume/confirm`,
    {
      authorization,
      registration_tx_hash: registrationHash,
      consume_tx_hash: consumeHash,
    },
    headers,
  );
  assert(consumed.execute === true, consumed.reason || "Verigate did not authorize payment execution");
  assert(consumed.wallet_transaction, "Verigate did not return the authorized payment transaction");

  return {
    authorization,
    registration_tx_hash: registrationHash,
    consume_tx_hash: consumeHash,
    arc_authority_evidence: consumed.arc_authority_evidence,
    wallet_transaction: consumed.wallet_transaction,
    payment_broadcast_required: true,
  };
}

/**
 * Broadcast only the payment returned by authorizeArcPayment.
 * Call this from a separate, explicit user action after reviewing the tx.
 */
export async function broadcastAuthorizedArcPayment({ provider, walletTransaction }) {
  await ensureArc(provider);
  await ensureTransactionAccount(provider, walletTransaction);
  return provider.request({
    method: "eth_sendTransaction",
    params: [txForWallet(walletTransaction)],
  });
}


/**
 * Ask Verigate to verify the wallet-broadcast payment against the original
 * signed authorization and the already-confirmed Registry consumption.
 * The API returns settled=true only after the matching USDC Transfer log is
 * present in a canonical finalized Arc block.
 */
export async function confirmArcPayment({
  provider,
  apiBaseUrl,
  authorization,
  registration_tx_hash,
  consume_tx_hash,
  payment_tx_hash,
  fetchImpl = globalThis.fetch,
  headers = {},
  receiptWait = {},
}) {
  assert(typeof apiBaseUrl === "string" && apiBaseUrl.length > 0, "apiBaseUrl is required");
  assert(typeof fetchImpl === "function", "fetch implementation is required");
  assert(authorization && typeof authorization === "object", "signed authorization is required");
  assert(typeof registration_tx_hash === "string", "registration transaction hash is required");
  assert(typeof consume_tx_hash === "string", "consumption transaction hash is required");
  assert(typeof payment_tx_hash === "string", "payment transaction hash is required");
  await ensureArc(provider);
  await waitForReceipt(provider, payment_tx_hash, receiptWait);

  const result = await postJson(
    fetchImpl,
    `${apiBaseUrl.replace(/\/$/, "")}/v1/integrations/arc/payment/confirm`,
    {
      authorization,
      registration_tx_hash,
      consume_tx_hash,
      payment_tx_hash,
    },
    headers,
  );
  assert(result.settled === true, result.reason || "Verigate did not confirm Arc USDC settlement");
  assert(result.payment_settlement?.verified === true, "Verigate returned no verified payment settlement evidence");
  return result;
}

export { ARC_CHAIN_ID, ARC_CHAIN_HEX };
