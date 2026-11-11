import fs from "node:fs";
import solc from "solc";
import { Interface, JsonRpcProvider, keccak256 } from "ethers";

const RPC_URL = process.env.VERIGATE_ARC_RPC_URL || "https://rpc.mainnet.arc.io";
const CONTRACT = (process.env.VERIGATE_ARC_REGISTRY_ADDRESS || "0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D").toLowerCase();
const EXPECTED_OWNER = (process.env.VERIGATE_ARC_EXECUTOR_ADDRESS || "0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C").toLowerCase();
const sourcePath = "contracts/arc-authority/src/VerigateAuthorityRegistry.sol";
const source = fs.readFileSync(sourcePath, "utf8");
const input = {
  language: "Solidity",
  sources: { [sourcePath]: { content: source } },
  settings: {
    optimizer: { enabled: true, runs: 200 },
    outputSelection: { "*": { "*": ["abi", "evm.deployedBytecode.object"] } },
  },
};
const output = JSON.parse(solc.compile(JSON.stringify(input)));
const errors = (output.errors || []).filter((entry) => entry.severity === "error");
if (errors.length) {
  for (const error of errors) process.stderr.write(error.formattedMessage + "\n");
  process.exit(1);
}
const artifact = output.contracts?.[sourcePath]?.VerigateAuthorityRegistry;
const runtime = artifact?.evm?.deployedBytecode?.object;
if (!runtime) throw new Error("Compiled runtime bytecode is missing");

const provider = new JsonRpcProvider(RPC_URL);
const network = await provider.getNetwork();
if (network.chainId !== 5042n) throw new Error(`Expected Arc chain 5042, received ${network.chainId}`);
const deployedCode = await provider.getCode(CONTRACT);
if (!deployedCode || deployedCode === "0x") throw new Error("No deployed Registry bytecode at configured address");

const compiledHash = keccak256("0x" + runtime);
const deployedHash = keccak256(deployedCode);
if (compiledHash !== deployedHash) {
  throw new Error(`Runtime bytecode mismatch: source=${compiledHash}, chain=${deployedHash}`);
}
const ownerData = await provider.call({ to: CONTRACT, data: "0x8da5cb5b" });
const owner = ("0x" + ownerData.slice(-40)).toLowerCase();
if (owner !== EXPECTED_OWNER) throw new Error(`Registry owner mismatch: expected ${EXPECTED_OWNER}, received ${owner}`);
const registryInterface = new Interface(artifact.abi);
const issuerData = registryInterface.encodeFunctionData("issuers", [EXPECTED_OWNER]);
const issuerResult = await provider.call({ to: CONTRACT, data: issuerData });
if (BigInt(issuerResult) !== 1n) throw new Error("Configured executor is not an enabled Registry issuer");
const finalized = await provider.getBlock("finalized");
if (!finalized || finalized.number == null || !finalized.hash) {
  throw new Error("Arc RPC did not return a verifiable finalized block");
}

process.stdout.write("Arc Registry deployment verification: PASS\n");
process.stdout.write(`chain_id=5042\ncontract=${CONTRACT}\nowner=${owner}\n`);
process.stdout.write(`compiled_runtime_keccak256=${compiledHash}\ndeployed_runtime_keccak256=${deployedHash}\n`);
process.stdout.write(`VERIGATE_ARC_REGISTRY_CODE_HASH=${deployedHash}\n`);
process.stdout.write(`finalized_block=${finalized.number} ${finalized.hash}\n`);
await provider.destroy();
