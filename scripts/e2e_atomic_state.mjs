import fs from "node:fs";
import path from "node:path";
import solc from "solc";
import ganache from "ganache";
import { ethers } from "ethers";

const root = path.resolve(process.cwd());
const guardSource = fs.readFileSync(path.join(root, "contracts", "VerigateAtomicStateGuard.sol"), "utf8").replace("\\uFEFF", "");
const oracleSource = `
pragma solidity ^0.8.24;
contract TestStateOracle {
    bytes32 public state;
    constructor(bytes32 initialState) { state = initialState; }
    function setState(bytes32 nextState) external { state = nextState; }
    function readState(bytes32) external view returns (bytes32) { return state; }
}
`;
const targetSource = `
pragma solidity ^0.8.24;
contract TestSideEffect {
    uint256 public count;
    event SideEffect(address indexed caller, uint256 count);
    function increment() external { count += 1; emit SideEffect(msg.sender, count); }
}
`;

const input = {
  language: "Solidity",
  sources: {
    "VerigateAtomicStateGuard.sol": { content: guardSource },
    "TestStateOracle.sol": { content: oracleSource },
    "TestSideEffect.sol": { content: targetSource },
  },
  settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: "paris", outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } } },
};
const compiled = JSON.parse(solc.compile(JSON.stringify(input)));
if (compiled.errors?.some(e => e.severity === "error")) {
  console.error(compiled.errors.filter(e => e.severity === "error"));
  process.exit(1);
}
function artifact(file, name) {
  const c = compiled.contracts[file][name];
  return { abi: c.abi, bytecode: "0x" + c.evm.bytecode.object };
}
const Guard = artifact("VerigateAtomicStateGuard.sol", "VerigateAtomicStateGuard");
const Oracle = artifact("TestStateOracle.sol", "TestStateOracle");
const Target = artifact("TestSideEffect.sol", "TestSideEffect");

const g = ganache.provider({ logging: { quiet: true }, chain: { chainId: 31337 } });
const provider = new ethers.BrowserProvider(g);
const signer = await provider.getSigner();

async function deploy(a, ...args) {
  const factory = new ethers.ContractFactory(a.abi, a.bytecode, signer);
  const c = await factory.deploy(...args);
  await c.waitForDeployment();
  return c;
}

const oldState = ethers.keccak256(ethers.toUtf8Bytes("state:v1"));
const newState = ethers.keccak256(ethers.toUtf8Bytes("state:v2"));
const oracle = await deploy(Oracle, oldState);
const target = await deploy(Target);
const guard = await deploy(Guard);
const reference = ethers.keccak256(ethers.toUtf8Bytes("resource:counter"));
const targetData = target.interface.encodeFunctionData("increment");

// Simulate stale authorization: authorization was bound to oldState, but the
// canonical state changes before the real side effect transaction executes.
await (await oracle.setState(newState)).wait();
let reverted = false;
try {
  await (await guard.execute(await target.getAddress(), 0, targetData, await oracle.getAddress(), reference, oldState)).wait();
} catch (e) {
  reverted = true;
}
const afterStale = await target.count();
if (!reverted || afterStale !== 0n) {
  throw new Error(`atomic stale-state test failed: reverted=${reverted} count=${afterStale}`);
}

// Fresh authorization bound to the current state succeeds and commits the effect.
await (await guard.execute(await target.getAddress(), 0, targetData, await oracle.getAddress(), reference, newState)).wait();
const afterFresh = await target.count();
if (afterFresh !== 1n) throw new Error(`fresh-state test failed: count=${afterFresh}`);

console.log(JSON.stringify({
  ok: true,
  chainId: 31337,
  guard: await guard.getAddress(),
  oracle: await oracle.getAddress(),
  target: await target.getAddress(),
  staleAuthorizationReverted: reverted,
  sideEffectAfterStaleAuthorization: afterStale.toString(),
  sideEffectAfterFreshAuthorization: afterFresh.toString(),
}, null, 2));


