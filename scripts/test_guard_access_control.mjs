import fs from "node:fs";
import path from "node:path";
import solc from "solc";
import ganache from "ganache";
import { ethers } from "ethers";

const root = path.resolve(process.cwd());
const guardSource = fs.readFileSync(path.join(root, "contracts", "VerigateAtomicStateGuard.sol"), "utf8").replace(/^\uFEFF/, "");
const helperSource = `
pragma solidity ^0.8.24;
contract TestStateOracle {
    bytes32 public state;
    constructor(bytes32 s) { state = s; }
    function setState(bytes32 s) external { state = s; }
    function readState(bytes32) external view returns (bytes32) { return state; }
}
contract LyingOracle {
    bytes32 public answer;
    constructor(bytes32 a) { answer = a; }
    function readState(bytes32) external view returns (bytes32) { return answer; }
}
// A protocol that trusts the guard's address, the case that matters.
contract GuardOnlyVault {
    address public immutable guard;
    uint256 public privilegedCount;
    constructor(address g) { guard = g; }
    function privilegedAction() external { require(msg.sender == guard, "only guard"); privilegedCount += 1; }
    receive() external payable {}
}
`;
const compiled = JSON.parse(solc.compile(JSON.stringify({
  language: "Solidity",
  sources: { "Guard.sol": { content: guardSource }, "Helpers.sol": { content: helperSource } },
  settings: { optimizer: { enabled: true, runs: 200 }, evmVersion: "paris", outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } } },
})));
if (compiled.errors?.some(e => e.severity === "error")) { console.error(compiled.errors.filter(e => e.severity === "error")); process.exit(1); }
const art = (f, n) => ({ abi: compiled.contracts[f][n].abi, bytecode: "0x" + compiled.contracts[f][n].evm.bytecode.object });
const Guard = art("Guard.sol", "VerigateAtomicStateGuard");
const Oracle = art("Helpers.sol", "TestStateOracle");
const Liar = art("Helpers.sol", "LyingOracle");
const Vault = art("Helpers.sol", "GuardOnlyVault");

const provider = new ethers.BrowserProvider(ganache.provider({ logging: { quiet: true }, chain: { chainId: 31337 } }));
const executor = await provider.getSigner(0);
const attacker = await provider.getSigner(1);
const executorAddress = await executor.getAddress();

async function deploy(a, signer, ...args) {
  const c = await new ethers.ContractFactory(a.abi, a.bytecode, signer).deploy(...args);
  await c.waitForDeployment();
  return c;
}
async function expectDeployRevert(label, fn) {
  try { await fn(); } catch { return "reverted"; }
  throw new Error(`${label}: expected the deployment to revert`);
}
// Calls a guard method and requires it to revert: first via eth_call (to read the
// custom error name where the node exposes it), then as a real transaction (must revert on chain).
async function expectRevert(label, contract, method, args, name, overrides = {}) {
  let got = "";
  try {
    await contract[method].staticCall(...args, overrides);
  } catch (e) {
    got = e?.revert?.name ?? "";
    const data = e?.data ?? e?.info?.error?.data ?? e?.error?.data;
    if (!got && typeof data === "string" && data.startsWith("0x")) {
      try { got = contract.interface.parseError(data)?.name ?? ""; } catch {}
    }
    if (name && got && got !== name) throw new Error(`${label}: expected ${name}, got ${got}`);
    got = got || "reverted";
    let sentReverted = false;
    try { await (await contract[method](...args, { ...overrides, gasLimit: 800000 })).wait(); } catch { sentReverted = true; }
    if (!sentReverted) throw new Error(`${label}: the transaction did not revert on chain`);
    return got;
  }
  throw new Error(`${label}: expected a revert but the call succeeded`);
}

const v1 = ethers.keccak256(ethers.toUtf8Bytes("state:v1"));
const v2 = ethers.keccak256(ethers.toUtf8Bytes("state:v2"));
const ref = ethers.keccak256(ethers.toUtf8Bytes("resource:vault"));
const results = {};

results.zeroExecutorRejected = await expectDeployRevert("zero executor", async () => { const c = await new ethers.ContractFactory(Guard.abi, Guard.bytecode, executor).deploy(ethers.ZeroAddress); return c.deploymentTransaction(); });

const guard = await deploy(Guard, executor, executorAddress);
const guardAddress = await guard.getAddress();
const oracle = await deploy(Oracle, executor, v1);
const liar = await deploy(Liar, attacker, v2);
const vault = await deploy(Vault, executor, guardAddress);
const vaultAddress = await vault.getAddress();
const liarAddress = await liar.getAddress();
const oracleAddress = await oracle.getAddress();
const data = vault.interface.encodeFunctionData("privilegedAction");

if ((await guard.executor()) !== executorAddress) throw new Error("executor() does not match the constructor argument");
results.executorRecorded = true;

// 1. Attacker with a lying oracle must not reach the guard-only vault.
results.attackerLyingOracle = await expectRevert("attacker + lying oracle", guard.connect(attacker), "execute", [vaultAddress, 0, data, liarAddress, ref, v2], "NotExecutor");
// 2. Attacker with an honest oracle and the correct state is still rejected.
results.attackerHonestOracle = await expectRevert("attacker + honest oracle", guard.connect(attacker), "execute", [vaultAddress, 0, data, oracleAddress, ref, v1], "NotExecutor");
if ((await vault.privilegedCount()) !== 0n) throw new Error("privileged action ran for a non-executor");

// 3. Executor with stale state reverts atomically.
await (await oracle.setState(v2)).wait();
results.executorStaleState = await expectRevert("executor + stale state", guard, "execute", [vaultAddress, 0, data, oracleAddress, ref, v1], "StateMismatch");
if ((await vault.privilegedCount()) !== 0n) throw new Error("side effect committed on stale state");

// 4. Executor with fresh state succeeds.
await (await guard.execute(vaultAddress, 0, data, oracleAddress, ref, v2)).wait();
if ((await vault.privilegedCount()) !== 1n) throw new Error("fresh execution did not commit");
results.executorFreshState = "ok";

// 5. value must equal msg.value: the guard's balance can never be spent.
results.valueMismatch = await expectRevert("value > msg.value", guard, "execute", [vaultAddress, 1, "0x", oracleAddress, ref, v2], "ValueMismatch");
await (await guard.execute(vaultAddress, 1, "0x", oracleAddress, ref, v2, { value: 1n })).wait();
if ((await provider.getBalance(vaultAddress)) !== 1n || (await provider.getBalance(guardAddress)) !== 0n) throw new Error("value forwarding is wrong");
results.valueForwarded = "ok";

console.log(JSON.stringify({ ok: true, chainId: 31337, executor: executorAddress, guard: guardAddress, results }, null, 2));
