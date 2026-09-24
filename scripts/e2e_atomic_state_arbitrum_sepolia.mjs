import fs from "node:fs";
import solc from "solc";
import { ethers } from "ethers";

const env = {};
for (const line of fs.readFileSync(".env", "utf8").split(/\r?\n/)) {
  const i = line.indexOf("=");
  if (i > 0) env[line.slice(0, i).trim()] = line.slice(i + 1).trim();
}
const provider = new ethers.JsonRpcProvider(env.ARB_SEPOLIA_RPC);
const signer = new ethers.Wallet(env.PRIVATE_KEY, provider);
const network = await provider.getNetwork();
if (network.chainId !== 421614n) throw new Error("Not Arbitrum Sepolia");

const guardSource = fs.readFileSync("contracts/VerigateAtomicStateGuard.sol", "utf8").replace(/^\uFEFF/, "");
const oracleSource = "pragma solidity ^0.8.24; contract LiveStateOracle { bytes32 public state; constructor(bytes32 s){state=s;} function setState(bytes32 s) external {state=s;} function readState(bytes32) external view returns(bytes32){return state;} }";
const targetSource = "pragma solidity ^0.8.24; contract LiveSideEffect { uint256 public count; event SideEffect(address indexed caller,uint256 count); function increment() external {count+=1;emit SideEffect(msg.sender,count);} }";
const input = { language:"Solidity", sources:{"Guard.sol":{content:guardSource},"Oracle.sol":{content:oracleSource},"Target.sol":{content:targetSource}}, settings:{optimizer:{enabled:true,runs:200},evmVersion:"paris",outputSelection:{"*":{"*":["abi","evm.bytecode.object"]}}} };
const compiled = JSON.parse(solc.compile(JSON.stringify(input)));
const errs = compiled.errors?.filter(e=>e.severity==="error") ?? [];
if (errs.length) throw new Error(JSON.stringify(errs));
const art=(f,n)=>{const c=compiled.contracts[f][n];return {abi:c.abi,bytecode:"0x"+c.evm.bytecode.object};};
const Guard=art("Guard.sol","VerigateAtomicStateGuard"), Oracle=art("Oracle.sol","LiveStateOracle"), Target=art("Target.sol","LiveSideEffect");
async function deploy(a,...args){const c=await new ethers.ContractFactory(a.abi,a.bytecode,signer).deploy(...args);const r=await c.deploymentTransaction().wait();return {c,address:await c.getAddress(),tx:r.hash};}
const oldState=ethers.keccak256(ethers.toUtf8Bytes("state:v1"));
const newState=ethers.keccak256(ethers.toUtf8Bytes("state:v2"));
const reference=ethers.keccak256(ethers.toUtf8Bytes("resource:live-counter"));
const oracle=await deploy(Oracle,oldState);
const target=await deploy(Target);
const guard=await deploy(Guard);
const oc=new ethers.Contract(oracle.address,Oracle.abi,signer);
const tc=new ethers.Contract(target.address,Target.abi,signer);
const gc=new ethers.Contract(guard.address,Guard.abi,signer);
const stateReceipt=await (await oc.setState(newState)).wait();
const data=tc.interface.encodeFunctionData("increment");
let reverted=false; let staleError="";try {
  await (await gc.execute(target.address,0,data,oracle.address,reference,oldState)).wait();
} catch (e) {
  reverted=true;
  staleError=String(e.shortMessage||e.message||e).slice(0,220);
}
const afterStale=await tc.count();
if (!reverted || afterStale !== 0n) throw new Error("stale-state proof failed");
const freshReceipt=await (await gc.execute(target.address,0,data,oracle.address,reference,newState)).wait();
const afterFresh=await tc.count();
if (afterFresh !== 1n) throw new Error("fresh-state proof failed");
console.log(JSON.stringify({
  ok:true,
  chainId:Number(network.chainId),
  network:"arbitrum-sepolia",
  deployer:signer.address,
  oracle:oracle.address, oracleDeployTx:oracle.tx,
  target:target.address, targetDeployTx:target.tx,
  guard:guard.address, guardDeployTx:guard.tx,
  stateChangeTx:stateReceipt.hash,
  staleAuthorizationReverted:reverted,
  staleError,
  sideEffectAfterStaleAuthorization:afterStale.toString(),
  freshExecutionTx:freshReceipt.hash,
  sideEffectAfterFreshAuthorization:afterFresh.toString()
},null,2));
