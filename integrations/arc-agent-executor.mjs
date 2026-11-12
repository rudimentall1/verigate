/**
 * Headless Arc payment executor for autonomous agents and backend workers.
 *
 * The Registry issuer signer is separate from the agent executor signer:
 * - issuerSigner registers the one-time authorization (operator/KMS boundary);
 * - agentSigner consumes it and broadcasts the exact authorized USDC payment.
 *
 * Neither signer belongs inside the Verigate API process. Implementations may
 * wrap an HSM/KMS or policy-controlled remote signer, provided they expose
 * getAddress() and sendTransaction(tx).
 */

const ARC_CHAIN_ID = 5042;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function normalizeAddress(value, field) {
  assert(
    typeof value === "string" && /^0x[0-9a-fA-F]{40}$/.test(value),
    `${field} must be a 20-byte EVM address`,
  );
  return value.toLowerCase();
}

function normalizeHash(value, field) {
  assert(
    typeof value === "string" && /^0x[0-9a-fA-F]{64}$/.test(value),
    `${field} must be a 32-byte transaction hash`,
  );
  return value.toLowerCase();
}

function toSignerTransaction(transaction, signerAddress, label) {
  assert(transaction && typeof transaction === "object", `${label} transaction is missing`);
  const expectedFrom = normalizeAddress(transaction.from, `${label} transaction from`);
  assert(expectedFrom === signerAddress, `${label} signer does not match transaction from address`);
  assert(
    typeof transaction.to === "string" && /^0x[0-9a-fA-F]{40}$/.test(transaction.to),
    `${label} transaction destination is invalid`,
  );
  assert(typeof transaction.data === "string" && /^0x(?:[0-9a-fA-F]{2})*$/.test(transaction.data), `${label} transaction data is invalid`);
  const chainId = Number(BigInt(transaction.chainId));
  assert(chainId === ARC_CHAIN_ID, `${label} transaction must target Arc Mainnet (5042)`);
  const value = typeof transaction.value === "string" ? BigInt(transaction.value) : BigInt(transaction.value ?? 0);
  assert(value >= 0n, `${label} transaction native value is invalid`);
  return {
    chainId,
    to: transaction.to,
    data: transaction.data,
    value,
  };
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

async function submitAndConfirm(signer, transaction, label) {
  assert(signer && typeof signer.getAddress === "function", `${label} signer must expose getAddress()`);
  assert(typeof signer.sendTransaction === "function", `${label} signer must expose sendTransaction()`);
  const signerAddress = normalizeAddress(await signer.getAddress(), `${label} signer address`);
  const tx = toSignerTransaction(transaction, signerAddress, label);
  const response = await signer.sendTransaction(tx);
  const transactionHash = normalizeHash(response?.hash, `${label} transaction response hash`);
  assert(typeof response.wait === "function", `${label} signer response must expose wait()`);
  const receipt = await response.wait();
  const status = receipt?.status;
  assert(status === 1 || status === "1" || status === "0x1", `${label} transaction failed: ${transactionHash}`);
  return transactionHash;
}

/**
 * Execute one Arc USDC payment without a browser or interactive wallet prompt.
 *
 * authorizationRequest must be signed by the agent identity key using
 * build_arc_payment_authorization_request() from integrations.agent_sdk.
 * issuerSigner must be an operator-controlled issuer/KMS signer, not the
 * agent's payer signer. agentSigner must control the signed payment sender.
 */
export async function executeAuthorizedArcPayment({
  provider,
  issuerSigner,
  agentSigner,
  apiBaseUrl,
  authorizationRequest,
  fetchImpl = globalThis.fetch,
  headers = {},
}) {
  assert(provider && typeof provider.getNetwork === "function", "an ethers-compatible JSON-RPC provider is required");
  assert(typeof apiBaseUrl === "string" && apiBaseUrl.length > 0, "apiBaseUrl is required");
  assert(typeof fetchImpl === "function", "fetch implementation is required");
  assert(authorizationRequest && typeof authorizationRequest === "object", "signed agent authorization request is required");
  assert(issuerSigner && typeof issuerSigner.getAddress === "function", "operator issuer signer is required");
  assert(agentSigner && typeof agentSigner.getAddress === "function", "agent executor signer is required");

  const network = await provider.getNetwork();
  assert(BigInt(network.chainId) === BigInt(ARC_CHAIN_ID), "provider must be connected to Arc Mainnet (chain ID 5042)");

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
  assert(registrationTx, "Verigate did not return a Registry registration transaction");

  // Registration is an issuer action. This signer is operator/KMS controlled.
  const registrationHash = await submitAndConfirm(issuerSigner, registrationTx, "Registry registration");
  const registered = await postJson(
    fetchImpl,
    `${base}/v1/integrations/arc/registration/confirm`,
    { authorization, registration_tx_hash: registrationHash },
    headers,
  );
  assert(registered.registered === true, "Verigate did not confirm Registry registration");
  const consumeTx = registered.consume_transaction;
  assert(consumeTx, "Verigate did not return a Registry consumption transaction");

  // Consumption and payment are executed by the agent's own EVM account.
  const consumeHash = await submitAndConfirm(agentSigner, consumeTx, "agent executor Registry consumption");
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
  assert(consumed.execute === true, consumed.reason || "Verigate denied execution");
  assert(consumed.wallet_transaction, "Verigate did not return the exact authorized payment transaction");

  const paymentHash = await submitAndConfirm(agentSigner, consumed.wallet_transaction, "agent executor USDC payment");
  const settlement = await postJson(
    fetchImpl,
    `${base}/v1/integrations/arc/payment/confirm`,
    {
      authorization,
      registration_tx_hash: registrationHash,
      consume_tx_hash: consumeHash,
      payment_tx_hash: paymentHash,
    },
    headers,
  );
  assert(settlement.settled === true, settlement.reason || "Verigate did not confirm USDC settlement");
  assert(settlement.payment_settlement?.verified === true, "Verigate returned no verified settlement evidence");

  return {
    authorization_id: authorization.payload?.authorization_id,
    issuer: normalizeAddress(registrationTx.from, "Registry issuer"),
    executor: normalizeAddress(consumeTx.from, "agent executor"),
    registration_tx_hash: registrationHash,
    consume_tx_hash: consumeHash,
    payment_tx_hash: paymentHash,
    arc_authority_evidence: consumed.arc_authority_evidence,
    payment_settlement: settlement.payment_settlement,
    settled: true,
  };
}

export { ARC_CHAIN_ID };
