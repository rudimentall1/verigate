/**
 * Ethers v6 broadcast adapter for the constrained Arc signer.
 *
 * The adapter accepts only transactions already derived by arc-constrained-signer.
 * It pins Arc Mainnet and the Registry runtime code hash at initialization,
 * serializes broadcasts to avoid local nonce races, and fails closed on fee,
 * estimate, receipt or settlement inconsistencies.
 */
import { JsonRpcProvider, Wallet, keccak256, id } from "ethers";
import {
  ARC_CHAIN_ID, normalizeAddress, validateFeePolicy,
} from "./arc-constrained-signer.mjs";

export const ARC_REGISTRY_ADDRESS = "0x4D09CdD490c1Ce48BCB6DA5c1A6Bf41E2f5e853D";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

export async function createArcEthersAdapter({
  rpcUrl,
  privateKey,
  registryAddress,
  expectedRegistryCodeHash,
  role,
  issuerAddress,
  feePolicy,
  confirmations = 1,
  provider: injectedProvider,
  wallet: injectedWallet,
}) {
  assert(injectedProvider || (typeof rpcUrl === "string" && rpcUrl.startsWith("https://")), "HTTPS Arc RPC URL is required");
  assert(injectedWallet || (typeof privateKey === "string" && /^0x[0-9a-fA-F]{64}$/.test(privateKey)), "EVM private key must be supplied through the isolated signer process");
  assert(typeof expectedRegistryCodeHash === "string" && /^0x[0-9a-fA-F]{64}$/.test(expectedRegistryCodeHash), "pinned Registry runtime code hash is required");
  assert(feePolicy && feePolicy.gasLimit !== undefined, "complete signer fee policy is required");
  assert(Number.isSafeInteger(confirmations) && confirmations >= 1, "confirmations must be a positive integer");
  const registry = normalizeAddress(registryAddress, "Arc Registry");
  assert(registry === ARC_REGISTRY_ADDRESS.toLowerCase(), "Registry address differs from the verified Arc Mainnet deployment");
  assert(role === "issuer" || role === "agent", "signer role must be issuer or agent");
  const issuer = normalizeAddress(issuerAddress, "configured Registry issuer");

  const provider = injectedProvider || new JsonRpcProvider(rpcUrl, ARC_CHAIN_ID, { staticNetwork: true });
  const wallet = injectedWallet || new Wallet(privateKey, provider);
  const signer = injectedWallet ? injectedWallet : wallet;
  const address = normalizeAddress(await signer.getAddress(), "signer address");
  let initialized = false;
  let queue = Promise.resolve();

  async function initialize() {
    const network = await provider.getNetwork();
    assert(Number(network.chainId) === ARC_CHAIN_ID, "RPC endpoint is not Arc Mainnet (5042)");
    const code = await provider.getCode(registry);
    assert(typeof code === "string" && code !== "0x" && code.length > 2, "Arc Registry has no runtime bytecode");
    assert(keccak256(code).toLowerCase() === expectedRegistryCodeHash.toLowerCase(), "Arc Registry runtime bytecode hash mismatch");
    if (role === "issuer") assert(address === issuer, "issuer signer address differs from configured Registry issuer");
    if (role === "agent") assert(address !== issuer, "agent signer must use a distinct address from the Registry issuer");
    const issuerCall = id("issuers(address)").slice(0, 10) + issuer.slice(2).padStart(64, "0");
    const issuerEnabled = await provider.call({ to: registry, data: issuerCall });
    assert(BigInt(issuerEnabled) === 1n, "configured Registry issuer is not enabled on Arc");
    initialized = true;
    return { address, chainId: ARC_CHAIN_ID, registry, issuer, issuerEnabled: true, registryCodeHash: keccak256(code) };
  }

  async function execute(input) {
    assert(initialized, "Arc signer adapter must pass startup verification before use");
    const tx = input?.transaction;
    assert(typeof input?.validateBeforeBroadcast === "function", "authorization revalidation callback is required");
    assert(typeof input?.onBroadcast === "function", "durable broadcast journal callback is required");
    assert(tx && Number(tx.chainId) === ARC_CHAIN_ID, "derived transaction is not bound to Arc Mainnet");
    assert(normalizeAddress(tx.to, "derived transaction destination") === tx.to.toLowerCase(), "derived destination is malformed");
    assert(typeof tx.data === "string" && /^0x(?:[0-9a-fA-F]{2})*$/.test(tx.data), "derived calldata is malformed");
    assert(BigInt(tx.value) === 0n, "native value transfer is forbidden");

    const feeData = await provider.getFeeData();
    const limits = validateFeePolicy(feePolicy, feeData);
    const estimate = await provider.estimateGas({
      from: address, to: tx.to, data: tx.data, value: 0n,
    });
    assert(estimate > 0n && estimate <= limits.gasLimit, "estimated gas exceeds signer gas limit");

    const nonce = await provider.getTransactionCount(address, "pending");
    await input.validateBeforeBroadcast();
    const response = await signer.sendTransaction({
      chainId: ARC_CHAIN_ID, nonce, type: 2,
      to: tx.to, data: tx.data, value: 0n,
      gasLimit: limits.gasLimit,
      maxFeePerGas: limits.maxFeePerGas,
      maxPriorityFeePerGas: limits.maxPriorityFeePerGas,
    });
    assert(response && typeof response.hash === "string", "RPC returned no transaction hash");
    await input.onBroadcast(response.hash);
    const receipt = await response.wait(confirmations);
    assert(receipt && Number(receipt.status) === 1, "Arc transaction receipt is missing or reverted");
    assert(String(receipt.hash || receipt.transactionHash).toLowerCase() === response.hash.toLowerCase(), "receipt hash does not match submitted transaction");
    assert(normalizeAddress(receipt.from, "receipt sender") === address, "receipt sender does not match isolated signer");
    assert(normalizeAddress(receipt.to, "receipt destination") === normalizeAddress(tx.to, "derived transaction destination"), "receipt destination does not match derived transaction");
    assert(Number.isSafeInteger(Number(receipt.blockNumber)) && Number(receipt.blockNumber) > 0, "receipt block number is invalid");
    const effectiveGasPrice = receipt.effectiveGasPrice ?? receipt.gasPrice;
    assert(receipt.gasUsed != null && effectiveGasPrice != null, "receipt lacks actual fee fields");
    const actualNativeCost = (BigInt(receipt.gasUsed) * BigInt(effectiveGasPrice)).toString();
    assert(BigInt(actualNativeCost) <= limits.maxNativeCost, "actual native cost exceeded per-operation ceiling");
    return {
      txHash: response.hash,
      actualNativeCost,
      blockNumber: Number(receipt.blockNumber),
      confirmations,
      status: "success",
    };
  }

  return {
    address,
    initialize,
    executeOperation(input) {
      const task = queue.then(() => execute(input));
      queue = task.catch(() => {});
      return task;
    },
  };
}
