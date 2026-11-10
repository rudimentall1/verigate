/**
 * Minimal EIP-1193 client for Verigate's Arc Authority Registry flow.
 *
 * This module never broadcasts the payment automatically. It performs the
 * two registry transactions, obtains Verigate's final payment transaction,
 * and returns it for a separate, explicit user-confirmed wallet action.
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

async function ensureExecutorAccount(provider, transaction) {
  const expected = transaction?.from;
  assert(typeof expected === "string", "registry transaction executor is missing");
  const accounts = await provider.request({ method: "eth_accounts" });
  assert(Array.isArray(accounts), "wallet did not return its connected accounts");
  assert(
    accounts.some(account => typeof account === "string" && account.toLowerCase() === expected.toLowerCase()),
    `connect the configured Verigate executor wallet (${expected}) before continuing`,
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
    if (receipt) return receipt;
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

  await ensureExecutorAccount(provider, registrationTx);
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

  await ensureExecutorAccount(provider, consumeTx);
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
  await ensureExecutorAccount(provider, walletTransaction);
  return provider.request({
    method: "eth_sendTransaction",
    params: [txForWallet(walletTransaction)],
  });
}

export { ARC_CHAIN_ID, ARC_CHAIN_HEX };
