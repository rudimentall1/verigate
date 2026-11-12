#!/usr/bin/env node
/**
 * Production entrypoint for one isolated Arc signer role.
 * Run issuer and agent instances under different Linux users and key files.
 */
import { readFileSync, lstatSync } from "node:fs";
import { OperationJournal, ARC_CHAIN_ID } from "../integrations/arc-constrained-signer.mjs";
import { createArcSignerSocketServer } from "../integrations/arc-signer-socket.mjs";
import { createArcEthersAdapter, ARC_REGISTRY_ADDRESS } from "../integrations/arc-ethers-signer-adapter.mjs";

function required(name) {
  const value = process.env[name];
  if (!value || !value.trim()) throw new Error(name + " is required");
  return value.trim();
}

function readProtectedFile(path, label, requirePrivateMode = false) {
  const stat = lstatSync(path);
  if (!stat.isFile()) throw new Error(label + " must be a regular file, not a symlink");
  if (typeof process.getuid === "function" && stat.uid !== process.getuid()) {
    throw new Error(label + " must be owned by the signer process user");
  }
  if (requirePrivateMode && (stat.mode & 0o077) !== 0) {
    throw new Error(label + " permissions are too broad; require mode 0600 or stricter");
  }
  return readFileSync(path, "utf8").trim();
}

function integerEnv(name, fallback) {
  const value = process.env[name] ?? fallback;
  if (!/^[1-9][0-9]*$/.test(value)) throw new Error(name + " must be a positive integer");
  return value;
}

async function main() {
  if (process.platform !== "linux") throw new Error("Arc signer daemon is supported only on Linux");
  const role = required("VERIGATE_SIGNER_ROLE");
  if (role !== "issuer" && role !== "agent") throw new Error("VERIGATE_SIGNER_ROLE must be issuer or agent");

  const socketPath = required("VERIGATE_SIGNER_SOCKET");
  const journalPath = required("VERIGATE_SIGNER_JOURNAL");
  const privateKeyPath = required("VERIGATE_SIGNER_PRIVATE_KEY_FILE");
  const publicKeyPath = required("VERIGATE_AUTH_PUBLIC_KEY_FILE");
  const privateKey = readProtectedFile(privateKeyPath, "Signer private key", true);
  if (!/^0x[0-9a-fA-F]{64}$/.test(privateKey)) throw new Error("Signer private key file must contain one 32-byte EVM key");
  const publicKeyPem = readProtectedFile(publicKeyPath, "Verigate authorization public key");
  const issuerAddress = required("VERIGATE_ARC_ISSUER_ADDRESS");
  const expectedRegistryCodeHash = required("VERIGATE_ARC_REGISTRY_CODE_HASH");
  const feePolicy = {
    gasLimit: integerEnv("VERIGATE_SIGNER_GAS_LIMIT"),
    maxFeePerGas: integerEnv("VERIGATE_SIGNER_MAX_FEE_PER_GAS"),
    maxPriorityFeePerGas: integerEnv("VERIGATE_SIGNER_MAX_PRIORITY_FEE_PER_GAS"),
    maxNativeCost: integerEnv("VERIGATE_SIGNER_MAX_NATIVE_COST"),
    dailyNativeBudget: integerEnv("VERIGATE_SIGNER_DAILY_NATIVE_BUDGET"),
  };
  const confirmations = Number(integerEnv("VERIGATE_SIGNER_CONFIRMATIONS", "1"));

  const adapter = await createArcEthersAdapter({
    rpcUrl: required("VERIGATE_ARC_RPC_URL"),
    privateKey,
    registryAddress: ARC_REGISTRY_ADDRESS,
    expectedRegistryCodeHash,
    feePolicy,
    confirmations,
  });
  const identity = await adapter.initialize();
  const journal = new OperationJournal(journalPath);
  const service = createArcSignerSocketServer({
    socketPath, role, authorizationPublicKeyPem: publicKeyPem,
    registryAddress: ARC_REGISTRY_ADDRESS,
    signerAddress: identity.address,
    issuerAddress,
    journal, feePolicy,
    executeOperation: adapter.executeOperation,
  });

  await service.listen();
  process.stdout.write(JSON.stringify({
    event: "arc_signer_ready",
    role,
    address: identity.address,
    chainId: ARC_CHAIN_ID,
    registry: identity.registry,
    registryCodeHash: identity.registryCodeHash,
    socketPath,
  }) + "\n");

  let stopping = false;
  const stop = async () => {
    if (stopping) return;
    stopping = true;
    await service.close();
    process.exit(0);
  };
  process.on("SIGTERM", () => { void stop(); });
  process.on("SIGINT", () => { void stop(); });
}

main().catch(error => {
  process.stderr.write(JSON.stringify({ event: "arc_signer_startup_failed", error: error?.message || "startup failed" }) + "\n");
  process.exitCode = 1;
});
