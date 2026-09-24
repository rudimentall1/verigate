import fs from "node:fs";
import { ethers } from "ethers";

const env = {};
for (const line of fs.readFileSync(".env", "utf8").split(/\r?\n/)) {
  const i = line.indexOf("=");
  if (i > 0) env[line.slice(0, i).trim()] = line.slice(i + 1).trim();
}
if (!env.ARB_SEPOLIA_RPC || !env.PRIVATE_KEY) throw new Error("missing signer environment");

const { tx } = JSON.parse(fs.readFileSync(0, "utf8"));
if (!tx || tx.chain_id !== 421614) throw new Error("unexpected chain_id");
if (typeof tx.to !== "string" || !/^0x[0-9a-fA-F]{40}$/.test(tx.to)) throw new Error("invalid tx.to");
if (typeof tx.data !== "string" || !/^0x[0-9a-fA-F]*$/.test(tx.data)) throw new Error("invalid tx.data");
if (!Number.isSafeInteger(tx.value_wei) || tx.value_wei < 0) throw new Error("invalid tx.value_wei");

const provider = new ethers.JsonRpcProvider(env.ARB_SEPOLIA_RPC);
const signer = new ethers.Wallet(env.PRIVATE_KEY, provider);
if ((await provider.getNetwork()).chainId !== 421614n) throw new Error("RPC is not Arbitrum Sepolia");

const sent = await signer.sendTransaction({
  chainId: 421614,
  to: tx.to,
  value: BigInt(tx.value_wei),
  data: tx.data
});
const receipt = await sent.wait();
process.stdout.write(JSON.stringify({
  transaction_hash: sent.hash,
  from: signer.address,
  status: receipt.status,
  block_number: receipt.blockNumber,
  gas_used: receipt.gasUsed.toString()
}));
