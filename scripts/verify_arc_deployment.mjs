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
} finally {
  await provider.destroy();
}
