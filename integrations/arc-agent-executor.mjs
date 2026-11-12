/**
 * Headless Arc payment executor for autonomous agents and backend workers.
 *
 * The issuer registers the one-time authorization. The agent signer consumes
 * it and submits the exact payment. The API never receives either private key.
 */
import { createHash, createPublicKey, verify as verifySignature } from "node:crypto";

const ARC_CHAIN_ID = 5042;
const REGISTER_SELECTOR = "0xb267748a";
const CONSUME_SELECTOR = "0xbad56b75";
const ARC_USDC_ADDRESS = "0x3600000000000000000000000000000000000000";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function normalizeAddress(value, field) {
  assert(typeof value === "string" && /^0x[0-9a-fA-F]{40}$/.test(value), `${field} must be a 20-byte EVM address`);
  return value.toLowerCase();
}

function normalizeHash(value, field) {
  assert(typeof value === "string" && /^0x[0-9a-fA-F]{64}$/.test(value), `${field} must be a 32-byte transaction hash`);
  return value.toLowerCase();
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function word(value, field) {
  let number;
  try { number = BigInt(value); } catch { throw new Error(`${field} must be an unsigned integer`); }
  assert(number >= 0n && number < (1n << 256n), `${field} is outside uint256 range`);
  return number.toString(16).padStart(64, "0");
}

function addressWord(value, field) {
  return normalizeAddress(value, field).slice(2).padStart(64, "0");
}

function verifyAuthorization(authorization, pem) {
  assert(authorization && typeof authorization === "object", "Verigate execution authorization is missing");
  assert(authorization.algorithm === "Ed25519", "unsupported execution authorization signature algorithm");
  assert(authorization.payload && typeof authorization.payload === "object", "execution authorization payload is missing");
  assert(typeof authorization.signature === "string", "execution authorization signature is missing");
  let signature;
  try { signature = Buffer.from(authorization.signature, "base64"); } catch { throw new Error("execution authorization signature is malformed"); }
  assert(signature.length === 64, "execution authorization signature must be a 64-byte Ed25519 signature");
  const key = createPublicKey(pem);
  const valid = verifySignature(null, Buffer.from(canonicalJson(authorization.payload), "utf8"), key, signature);
  assert(valid, "Verigate execution authorization signature is invalid");
  const p = authorization.payload;
  assert(p.authorization_version === 1, "unsupported execution authorization version");
  assert(typeof p.authorization_id === "string" && /^[0-9a-f]{64}$/.test(p.authorization_id), "authorization_id must be a lowercase 32-byte hex value");
  assert(Number.isSafeInteger(p.expires_at) && p.expires_at > 0, "authorization expiry is invalid");
  assert(p.action && typeof p.action === "object", "signed authorized action is missing");
  const action = p.action;
  assert(action.network === "arc" && action.asset === "USDC" && action.action_type === "payment", "signed authorization is not an Arc USDC payment");
  const arc = action.metadata?.arc;
  assert(arc && Number(arc.chain_id) === ARC_CHAIN_ID && arc.asset === "USDC", "signed Arc network binding is invalid");
  assert(normalizeAddress(arc.token_address, "signed canonical USDC token") === ARC_USDC_ADDRESS, "signed token is not canonical Arc USDC");
  assert(arc.token_decimals === 6, "signed Arc USDC decimals must be 6");
  const evm = action.metadata?.evm_transaction;
  assert(evm && typeof evm === "object", "signed Arc payment transaction is missing");
  assert(Number(evm.chain_id) === ARC_CHAIN_ID, "signed payment must target Arc Mainnet");
  assert(normalizeAddress(evm.to, "signed USDC token destination") === ARC_USDC_ADDRESS, "signed payment destination is not canonical Arc USDC");
  assert(BigInt(evm.value_wei ?? 0) === 0n, "signed USDC payment must not transfer native value");
  const recipient = normalizeAddress(action.target, "signed payment recipient");
  assert(typeof action.amount_exact === "string" && /^\\d+(?:\\.\\d{1,6})?$/.test(action.amount_exact), "signed USDC amount_exact must be a decimal string with at most 6 places");
  const [whole, fraction = ""] = action.amount_exact.split(".");
  const amount = BigInt(whole) * 1000000n + BigInt(fraction.padEnd(6, "0") || "0");
  assert(amount > 0n && amount < (1n << 256n), "signed USDC amount is outside valid range");
  const expectedTransferData = "0xa9059cbb" + addressWord(recipient, "signed payment recipient") + word(amount, "signed USDC amount");
  assert(typeof evm.data === "string" && evm.data.toLowerCase() === expectedTransferData, "signed USDC calldata does not match the signed recipient and amount");
  return { payload: p, evm, expectedTransferData };
}

async function postJson(fetchImpl, url, body, headers) {
  const response = await fetchImpl(url, {
    method: "POST",
    headers: { "content-type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  let payload;
  try { payload = await response.json(); }
  catch { throw new Error(`Verigate returned a non-JSON response (HTTP ${response.status})`); }
  if (!response.ok) {
    const detail = payload?.detail || payload?.error || `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return payload;
}

function normalizeSignerTransaction(transaction, signerAddress, label, expected) {
  assert(transaction && typeof transaction === "object", `${label} transaction is missing`);
  const from = normalizeAddress(transaction.from, `${label} transaction from`);
  assert(from === signerAddress, `${label} signer does not match transaction from address`);
  const to = normalizeAddress(transaction.to, `${label} transaction destination`);
  assert(Number(BigInt(transaction.chainId)) === ARC_CHAIN_ID, `${label} transaction must target Arc Mainnet (5042)`);
  assert(typeof transaction.data === "string" && /^0x(?:[0-9a-fA-F]{2})*$/.test(transaction.data), `${label} transaction data is invalid`);
  const value = BigInt(transaction.value ?? 0);
  assert(value === 0n, `${label} transaction must not transfer native value`);
  assert(to === expected.to, `${label} transaction destination does not match independently derived destination`);
  assert(transaction.data.toLowerCase() === expected.data.toLowerCase(), `${label} transaction calldata does not match independently derived operation`);
  return { chainId: ARC_CHAIN_ID, to, data: transaction.data, value };
}

async function submitAndConfirm(signer, transaction, label, expected) {
  assert(signer && typeof signer.getAddress === "function", `${label} signer must expose getAddress()`);
  assert(typeof signer.sendTransaction === "function", `${label} signer must expose sendTransaction()`);
  const signerAddress = normalizeAddress(await signer.getAddress(), `${label} signer address`);
  const tx = normalizeSignerTransaction(transaction, signerAddress, label, expected);
  const response = await signer.sendTransaction(tx);
  const transactionHash = normalizeHash(response?.hash, `${label} transaction response hash`);
  assert(typeof response.wait === "function", `${label} signer response must expose wait()`);
  const receipt = await response.wait();
  assert(receipt?.status === 1 || receipt?.status === "1" || receipt?.status === "0x1", `${label} transaction failed: ${transactionHash}`);
  const minedHash = receipt?.hash ?? receipt?.transactionHash;
  if (minedHash != null) assert(normalizeHash(minedHash, `${label} receipt hash`) === transactionHash, `${label} receipt hash does not match submitted hash`);
  return transactionHash;
}

/**
 * Execute one Arc USDC payment. Public-key signature verification and exact
 * transaction derivation happen locally before any signer is asked to broadcast.
 */
export async function executeAuthorizedArcPayment({
  provider, issuerSigner, agentSigner, apiBaseUrl, authorizationRequest,
  verigatePublicKey, registryAddress, fetchImpl = globalThis.fetch, headers = {},
}) {
  assert(provider && typeof provider.getNetwork === "function", "an ethers-compatible JSON-RPC provider is required");
  assert(typeof apiBaseUrl === "string" && apiBaseUrl.length > 0, "apiBaseUrl is required");
  assert(typeof fetchImpl === "function", "fetch implementation is required");
  assert(typeof verigatePublicKey === "string" && verigatePublicKey.includes("BEGIN PUBLIC KEY"), "a pinned Verigate Ed25519 public key is required");
  assert(typeof registryAddress === "string" && /^0x[0-9a-fA-F]{40}$/.test(registryAddress), "a pinned Arc Registry address is required");
  assert(authorizationRequest && typeof authorizationRequest === "object", "signed agent authorization request is required");
  assert(issuerSigner && typeof issuerSigner.getAddress === "function", "operator issuer signer is required");
  assert(agentSigner && typeof agentSigner.getAddress === "function", "agent executor signer is required");

  const network = await provider.getNetwork();
  assert(BigInt(network.chainId) === BigInt(ARC_CHAIN_ID), "provider must be connected to Arc Mainnet (chain ID 5042)");
  const issuerAddress = normalizeAddress(await issuerSigner.getAddress(), "Registry issuer signer address");
  const agentAddress = normalizeAddress(await agentSigner.getAddress(), "agent executor signer address");
  assert(issuerAddress !== agentAddress, "Registry issuer and agent executor signers must be different addresses");

  const base = apiBaseUrl.replace(/\/$/, "");
  const authorized = await postJson(fetchImpl, `${base}/v1/integrations/arc/authorize`, authorizationRequest, headers);
  const authorization = authorized.execution_authorization;
  const registrationTx = authorized.arc_authority?.registration_transaction;
  const { payload, evm } = verifyAuthorization(authorization, verigatePublicKey);
  const pinnedRegistryAddress = normalizeAddress(registryAddress, "pinned Registry address");
  assert(normalizeAddress(authorized.arc_authority?.contract_address, "configured Registry address") === pinnedRegistryAddress, "Verigate Registry address does not match the pinned Registry");
  assert(normalizeAddress(authorized.arc_authority?.issuer, "Registry issuer") === issuerAddress, "configured Registry issuer does not match issuer signer");
  assert(normalizeAddress(authorized.arc_authority?.executor, "Registry executor") === agentAddress, "signed Registry executor does not match agent signer");
  assert(normalizeAddress(evm.from, "signed payment sender") === agentAddress, "agent signer does not match signed payment sender");

  // Match the server's language-neutral Registry hash: the Ed25519
  // signature commits to the canonical authorization payload.
  const intentHash = createHash("sha256").update(
    `verigate.arc.authority.registry:v2:${ARC_CHAIN_ID}:${pinnedRegistryAddress}:${authorization.algorithm}:${authorization.signature}`,
    "ascii",
  ).digest("hex");
  const authId = payload.authorization_id;
  const expectedRegistration = {
    to: pinnedRegistryAddress,
    data: REGISTER_SELECTOR + authId + intentHash + addressWord(agentAddress, "agent executor") + word(payload.expires_at, "authorization expiry"),
  };

  // The issuer may only register the exact signed authorization at the configured Registry.
  const registrationHash = await submitAndConfirm(
    issuerSigner, registrationTx, "Registry registration", expectedRegistration,
  );

  const registered = await postJson(fetchImpl, `${base}/v1/integrations/arc/registration/confirm`, {
    authorization, registration_tx_hash: registrationHash,
  }, headers);
  assert(registered.registered === true, "Verigate did not confirm Registry registration");
  const consumeTx = registered.consume_transaction;
  const expectedConsume = { to: pinnedRegistryAddress, data: CONSUME_SELECTOR + authId + intentHash };
  const consumeHash = await submitAndConfirm(
    agentSigner, consumeTx, "agent executor Registry consumption", expectedConsume,
  );

  const consumed = await postJson(fetchImpl, `${base}/v1/integrations/arc/consume/confirm`, {
    authorization, registration_tx_hash: registrationHash, consume_tx_hash: consumeHash,
  }, headers);
  assert(consumed.execute === true, consumed.reason || "Verigate denied execution");
  assert(consumed.wallet_transaction, "Verigate did not return the exact authorized payment transaction");

  const expectedPayment = {
    to: ARC_USDC_ADDRESS,
    data: verifyAuthorization(authorization, verigatePublicKey).expectedTransferData,
  };
  const paymentHash = await submitAndConfirm(
    agentSigner, consumed.wallet_transaction, "agent executor USDC payment", expectedPayment,
  );
  const settlement = await postJson(fetchImpl, `${base}/v1/integrations/arc/payment/confirm`, {
    authorization, registration_tx_hash: registrationHash,
    consume_tx_hash: consumeHash, payment_tx_hash: paymentHash,
  }, headers);
  assert(settlement.settled === true, settlement.reason || "Verigate did not confirm USDC settlement");
  assert(settlement.payment_settlement?.verified === true, "Verigate returned no verified settlement evidence");

  return {
    authorization_id: authId,
    issuer: issuerAddress,
    executor: agentAddress,
    registration_tx_hash: registrationHash,
    consume_tx_hash: consumeHash,
    payment_tx_hash: paymentHash,
    arc_authority_evidence: consumed.arc_authority_evidence,
    payment_settlement: settlement.payment_settlement,
    settled: true,
  };
}

export { ARC_CHAIN_ID };
