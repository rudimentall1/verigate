import fs from "node:fs";
import { Interface, JsonRpcProvider, keccak256, toUtf8Bytes } from "ethers";

const ROOT = "contracts/arc-authority/deployments/arc-mainnet";
const MANIFEST_PATH = `${ROOT}/deployment-manifest.json`;
const RUNTIME_PATH = `${ROOT}/VerigateAuthorityRegistry.runtime.hex`;
const SOURCE_PATH = `${ROOT}/VerigateAuthorityRegistry.deployed.sol`;

function requireCondition(condition, message) {
  if (!condition) throw new Error(message);
}

const manifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, "utf8"));
requireCondition(manifest.schema_version === 1, "Unsupported deployment manifest schema");
requireCondition(manifest.network === "Arc Mainnet", "Unexpected deployment network");
requireCondition(manifest.chain_id === 5042, "Manifest chain ID must be 5042");

const source = fs.readFileSync(SOURCE_PATH, "utf8");
const sourceHash = keccak256(toUtf8Bytes(source));
requireCondition(
  sourceHash.toLowerCase() === manifest.deployed_source.keccak256.toLowerCase(),
  `Archived deployment source hash mismatch: expected=${manifest.deployed_source.keccak256}, actual=${sourceHash}`,
);

const runtime = fs.readFileSync(RUNTIME_PATH, "utf8").trim();
requireCondition(/^0x(?:[0-9a-fA-F]{2})+$/.test(runtime), "Archived runtime bytecode is malformed");
const artifactHash = keccak256(runtime);
requireCondition(
  artifactHash.toLowerCase() === manifest.runtime.keccak256.toLowerCase(),
  `Archived artifact runtime hash mismatch: manifest=${manifest.runtime.keccak256}, artifact=${artifactHash}`,
);
requireCondition(
  (runtime.length - 2) / 2 === manifest.runtime.byte_length,
  "Archived runtime byte length does not match deployment manifest",
);

const RPC_URL = process.env.VERIGATE_ARC_RPC_URL || "https://rpc.mainnet.arc.io";
const CONTRACT = (process.env.VERIGATE_ARC_REGISTRY_ADDRESS || manifest.contract_address).toLowerCase();
const EXPECTED_OWNER = (process.env.VERIGATE_ARC_EXECUTOR_ADDRESS || manifest.expected_owner_and_issuer).toLowerCase();
const EXPECTED_CODE_HASH = (process.env.VERIGATE_ARC_REGISTRY_CODE_HASH || manifest.runtime.keccak256).toLowerCase();

requireCondition(CONTRACT === manifest.contract_address.toLowerCase(), "Configured Registry address differs from reviewed deployment manifest");
requireCondition(EXPECTED_OWNER === manifest.expected_owner_and_issuer.toLowerCase(), "Configured executor differs from reviewed deployment manifest");
requireCondition(EXPECTED_CODE_HASH === artifactHash.toLowerCase(), "Configured Registry code hash differs from reviewed deployment artifact");

const provider = new JsonRpcProvider(RPC_URL);
try {
  const network = await provider.getNetwork();
  requireCondition(network.chainId === 5042n, `Expected Arc chain 5042, received ${network.chainId}`);

  const deploymentTx = await provider.getTransaction(manifest.deployment_transaction);
  requireCondition(deploymentTx, "Registry deployment transaction was not found");
  requireCondition(deploymentTx.to === null, "Recorded Registry transaction is not a contract creation");
  requireCondition(deploymentTx.from.toLowerCase() === EXPECTED_OWNER, "Registry deployment sender does not match expected owner");
  requireCondition(deploymentTx.chainId === 5042n, "Registry deployment transaction has an unexpected chain ID");

  const deploymentReceipt = await provider.getTransactionReceipt(manifest.deployment_transaction);
  requireCondition(deploymentReceipt, "Registry deployment receipt was not found");
  requireCondition(deploymentReceipt.status === 1, "Registry deployment transaction failed");
  requireCondition(
    deploymentReceipt.contractAddress?.toLowerCase() === CONTRACT,
    `Deployment receipt contract address mismatch: expected=${CONTRACT}, actual=${deploymentReceipt.contractAddress}`,
  );
  requireCondition(
    deploymentReceipt.blockNumber === manifest.deployment_block,
    `Deployment block mismatch: expected=${manifest.deployment_block}, actual=${deploymentReceipt.blockNumber}`,
  );

  const deploymentBlock = await provider.getBlock(deploymentReceipt.blockNumber);
  requireCondition(deploymentBlock?.hash, "Canonical deployment block was not returned by Arc RPC");
  requireCondition(
    deploymentBlock.hash.toLowerCase() === deploymentReceipt.blockHash.toLowerCase(),
    "Deployment receipt block hash differs from canonical block hash",
  );

  const deployedCode = await provider.getCode(CONTRACT);
  requireCondition(deployedCode && deployedCode !== "0x", "No deployed Registry bytecode at configured address");
  const deployedHash = keccak256(deployedCode);
  requireCondition(
    deployedHash.toLowerCase() === artifactHash.toLowerCase(),
    `Deployed runtime mismatch: reviewed_artifact=${artifactHash}, chain=${deployedHash}`,
  );

  const registryInterface = new Interface([
    "function owner() view returns (address)",
    "function issuers(address) view returns (bool)",
  ]);
  const ownerData = registryInterface.encodeFunctionData("owner", []);
  const ownerResult = await provider.call({ to: CONTRACT, data: ownerData });
  const [owner] = registryInterface.decodeFunctionResult("owner", ownerResult);
  requireCondition(
    owner.toLowerCase() === EXPECTED_OWNER,
    `Registry owner mismatch: expected=${EXPECTED_OWNER}, actual=${owner}`,
  );

  const issuerData = registryInterface.encodeFunctionData("issuers", [EXPECTED_OWNER]);
  const issuerResult = await provider.call({ to: CONTRACT, data: issuerData });
  const [issuerEnabled] = registryInterface.decodeFunctionResult("issuers", issuerResult);
  requireCondition(issuerEnabled === true, "Configured executor is not an enabled Registry issuer");

  const finalized = await provider.getBlock("finalized");
  requireCondition(finalized?.number != null && finalized.hash, "Arc RPC did not return a verifiable finalized block");

  const activityInterface = new Interface([
    "event AuthorizationRegistered(bytes32 indexed authorizationId, bytes32 indexed intentHash, address indexed executor, uint64 validUntil, address issuer)",
    "event AuthorizationConsumed(bytes32 indexed authorizationId, bytes32 indexed intentHash, address indexed executor)",
    "function getAuthorization(bytes32 authorizationId) view returns (tuple(bytes32 intentHash, address executor, uint64 validUntil, uint64 registeredAt, bool consumed, bool revoked))",
  ]);
  const observedRegistryCalls = [];
  const consumedAuthorizationIds = new Set();

  for (const expectedCall of manifest.historical_registry_calls || []) {
    const block = await provider.getBlock(expectedCall.block, true);
    requireCondition(block?.hash, `Historical Registry activity block ${expectedCall.block} was not returned`);
    requireCondition(block.number <= finalized.number, `Historical Registry activity block ${expectedCall.block} is not finalized`);
    const transactions = block.prefetchedTransactions?.length
      ? block.prefetchedTransactions
      : await Promise.all((block.transactions || []).map((hash) => provider.getTransaction(hash)));
    const matches = transactions.filter((transaction) =>
      transaction
      && transaction.from?.toLowerCase() === EXPECTED_OWNER
      && transaction.to?.toLowerCase() === CONTRACT
      && transaction.data?.slice(0, 10).toLowerCase() === expectedCall.selector.toLowerCase()
    );
    requireCondition(
      matches.length === 1,
      `Expected exactly one ${expectedCall.method} call by the executor in block ${expectedCall.block}; found ${matches.length}`,
    );

    const transaction = matches[0];
    const receipt = await provider.getTransactionReceipt(transaction.hash);
    requireCondition(receipt, `Missing receipt for historical Registry call ${transaction.hash}`);
    requireCondition(receipt.status === 1, `Historical Registry call failed: ${transaction.hash}`);
    requireCondition(
      receipt.blockHash?.toLowerCase() === block.hash.toLowerCase(),
      `Historical Registry receipt is not in the canonical block: ${transaction.hash}`,
    );
    requireCondition(
      receipt.to?.toLowerCase() === CONTRACT && receipt.from?.toLowerCase() === EXPECTED_OWNER,
      `Historical Registry receipt sender/destination mismatch: ${transaction.hash}`,
    );

    const events = receipt.logs.flatMap((log) => {
      try {
        const parsed = activityInterface.parseLog(log);
        return parsed ? [{ log, parsed }] : [];
      } catch {
        return [];
      }
    }).filter(({ parsed }) => parsed.name === expectedCall.expected_event);
    requireCondition(
      events.length === 1,
      `Expected exactly one ${expectedCall.expected_event} event in ${transaction.hash}; found ${events.length}`,
    );

    const { parsed } = events[0];
    const authorizationId = parsed.args.authorizationId.toLowerCase();
    const intentHash = parsed.args.intentHash.toLowerCase();
    const executor = parsed.args.executor.toLowerCase();
    requireCondition(executor === EXPECTED_OWNER, `Unexpected Registry executor in ${transaction.hash}`);

    const callSummary = {
      block: expectedCall.block,
      transaction_hash: transaction.hash,
      method: expectedCall.method,
      event: expectedCall.expected_event,
      authorization_id: authorizationId,
      intent_hash: intentHash,
      executor,
    };

    if (expectedCall.expected_event === "AuthorizationRegistered") {
      const issuer = parsed.args.issuer.toLowerCase();
      const validUntil = parsed.args.validUntil;
      requireCondition(issuer === EXPECTED_OWNER, `Unexpected Registry issuer in ${transaction.hash}`);
      requireCondition(validUntil > 0n, `Invalid authorization expiry in ${transaction.hash}`);
      callSummary.issuer = issuer;
      callSummary.valid_until = validUntil.toString();
    } else if (expectedCall.expected_event === "AuthorizationConsumed") {
      consumedAuthorizationIds.add(authorizationId);
    }

    const stateData = activityInterface.encodeFunctionData("getAuthorization", [authorizationId]);
    const stateResult = await provider.call({ to: CONTRACT, data: stateData });
    const [state] = activityInterface.decodeFunctionResult("getAuthorization", stateResult);
    requireCondition(state.registeredAt > 0n, `Authorization is missing from Registry state: ${authorizationId}`);
    requireCondition(state.intentHash.toLowerCase() === intentHash, `Registry intent hash differs from event for ${authorizationId}`);
    requireCondition(state.executor.toLowerCase() === executor, `Registry executor differs from event for ${authorizationId}`);
    requireCondition(state.revoked === false, `Historical authorization is revoked: ${authorizationId}`);
    if (expectedCall.expected_event === "AuthorizationRegistered") {
      requireCondition(state.validUntil === parsed.args.validUntil, `Registry expiry differs from registration event for ${authorizationId}`);
    } else {
      requireCondition(state.consumed === true, `Consumed event has no consumed Registry state for ${authorizationId}`);
    }

    callSummary.registry_state = {
      registered_at: state.registeredAt.toString(),
      valid_until: state.validUntil.toString(),
      consumed: state.consumed,
      revoked: state.revoked,
    };
    observedRegistryCalls.push(callSummary);
  }

  for (const authorizationId of consumedAuthorizationIds) {
    const registerCall = observedRegistryCalls.find((entry) =>
      entry.authorization_id === authorizationId && entry.event === "AuthorizationRegistered"
    );
    requireCondition(
      registerCall,
      `Consumed authorization has no matching registration in the observed block set: ${authorizationId}`,
    );
  }

  requireCondition(
    finalized.number >= deploymentReceipt.blockNumber,
    "Registry deployment block is above the reported finalized head",
  );

  process.stdout.write("Arc Registry deployment verification: PASS\n");
  process.stdout.write(`chain_id=5042\ncontract=${CONTRACT}\nowner=${owner}\nissuer_enabled=true\n`);
  process.stdout.write(`deployment_tx=${manifest.deployment_transaction}\ndeployment_block=${deploymentReceipt.blockNumber}\n`);
  process.stdout.write(`deployment_block_hash=${deploymentBlock.hash}\nfinalized_block=${finalized.number} ${finalized.hash}\n`);
  process.stdout.write(`source_keccak256=${sourceHash}\nreviewed_artifact_runtime_keccak256=${artifactHash}\ndeployed_runtime_keccak256=${deployedHash}\n`);
  process.stdout.write(`VERIGATE_ARC_REGISTRY_CODE_HASH=${deployedHash}\n`);
  for (const call of observedRegistryCalls) {
    process.stdout.write(`historical_registry_call=${JSON.stringify(call)}\n`);
  }
} finally {
  await provider.destroy();
}
