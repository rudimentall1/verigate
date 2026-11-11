import fs from "node:fs";
import solc from "solc";

const sourcePath = "contracts/arc-authority/src/VerigateAuthorityRegistry.sol";
const source = fs.readFileSync(sourcePath, "utf8");
const input = {
  language: "Solidity",
  sources: { "VerigateAuthorityRegistry.sol": { content: source } },
  settings: {
    optimizer: { enabled: true, runs: 200 },
    outputSelection: {
      "*": {
        "*": ["abi", "evm.bytecode.object"]
      }
    }
  }
};

const output = JSON.parse(solc.compile(JSON.stringify(input)));
const errors = (output.errors || []).filter((entry) => entry.severity === "error");
if (errors.length) {
  for (const error of errors) process.stderr.write(error.formattedMessage + "\n");
  process.exit(1);
}

const artifact = output.contracts?.["VerigateAuthorityRegistry.sol"]?.VerigateAuthorityRegistry;
if (!artifact?.evm?.bytecode?.object) {
  throw new Error("Arc Authority Registry bytecode was not produced");
}

const functions = new Set(artifact.abi.filter((entry) => entry.type === "function").map((entry) => entry.name));
for (const required of ["registerAuthorization", "consumeAuthorization", "revokeAuthorization", "getAuthorization", "owner"]) {
  if (!functions.has(required)) throw new Error("Missing expected contract function: " + required);
}

if (!source.includes('block.timestamp < auth.validUntil')) {
  throw new Error("Contract expiry boundary must reject execution at expires_at");
}

process.stdout.write("Arc Authority Registry Solidity compile: PASS\n");
process.stdout.write("Required ABI and strict expiry boundary: PASS\n");
