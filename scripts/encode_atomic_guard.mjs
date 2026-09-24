import fs from "node:fs";
import crypto from "node:crypto";
import { ethers } from "ethers";

const input = JSON.parse(fs.readFileSync(0, "utf8"));
for (const key of ["target", "oracle", "reference", "expected"]) {
  if (typeof input[key] !== "string" || !input[key]) throw new Error(`missing ${key}`);
}
const iface = new ethers.Interface([
  "function execute(address target,uint256 value,bytes data,address oracle,bytes32 reference,bytes32 expected)"
]);
const targetData = input.target_data ?? "0x";
if (typeof targetData !== "string" || !/^0x[0-9a-fA-F]*$/.test(targetData)) throw new Error("invalid target_data");
const data = iface.encodeFunctionData("execute", [
  input.target, 0, targetData, input.oracle, input.reference, input.expected
]);
const data_sha256 = crypto.createHash("sha256").update(data, "utf8").digest("hex");
process.stdout.write(JSON.stringify({data, data_sha256}));
