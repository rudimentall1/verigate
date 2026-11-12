/**
 * Unix-domain transport for the constrained Arc signer.
 *
 * This module exposes only typed authorization operations. It never accepts
 * arbitrary transaction data or generic signing requests. The injected
 * executeOperation adapter must independently enforce fee policy, nonce
 * handling, chain ID, destination/data/value and receipt finality.
 */
import { createServer } from "node:net";
import { chmodSync, lstatSync, unlinkSync } from "node:fs";
import { deriveArcOperation } from "./arc-constrained-signer.mjs";

const MAX_REQUEST_BYTES = 64 * 1024;
const ALLOWED_OPERATIONS = new Set(["register", "consume", "payment"]);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function writeJson(socket, value) {
  if (!socket.destroyed) socket.end(JSON.stringify(value) + "\n");
}

export function createArcSignerSocketServer({
  socketPath,
  role,
  authorizationPublicKeyPem,
  registryAddress,
  signerAddress,
  issuerAddress,
  journal,
  feePolicy,
  executeOperation,
  now = () => Math.floor(Date.now() / 1000),
}) {
  assert(typeof socketPath === "string" && socketPath.startsWith("/"), "socketPath must be an absolute filesystem path");
  assert(role === "issuer" || role === "agent", "signer role must be issuer or agent");
  assert(typeof authorizationPublicKeyPem === "string" && authorizationPublicKeyPem.length > 0, "pinned authorization public key is required");
  assert(journal && typeof journal.reserve === "function" && typeof journal.markBroadcast === "function" && typeof journal.complete === "function", "durable operation journal is required");
  assert(typeof executeOperation === "function", "broadcast adapter is required");
  assert(feePolicy && feePolicy.maxNativeCost !== undefined && feePolicy.dailyNativeBudget !== undefined, "native fee budget is required");

  const server = createServer((socket) => {
    socket.setTimeout(10_000, () => socket.destroy());
    let input = "";
    let handled = false;

    socket.on("data", async (chunk) => {
      if (handled) return;
      input += chunk.toString("utf8");
      if (Buffer.byteLength(input, "utf8") > MAX_REQUEST_BYTES) {
        handled = true;
        writeJson(socket, { ok: false, error: "request exceeds 64 KiB limit" });
        return;
      }
      const newline = input.indexOf("\n");
      if (newline === -1) return;
      handled = true;
      if (input.slice(newline + 1).trim() !== "") {
        writeJson(socket, { ok: false, error: "exactly one JSON request is allowed per connection" });
        return;
      }
      try {
        const request = JSON.parse(input.slice(0, newline));
        assert(request && typeof request === "object" && !Array.isArray(request), "request must be a JSON object");
        assert(Object.keys(request).sort().join(",") === "authorization,operation", "request may contain only operation and authorization");
        assert(ALLOWED_OPERATIONS.has(request.operation), "unsupported signer operation");
        const derived = deriveArcOperation({
          role, operation: request.operation, authorization: request.authorization,
          publicKeyPem: authorizationPublicKeyPem, registryAddress, signerAddress,
          issuerAddress, now: now(),
        });
        const reservation = journal.reserve(derived.authorizationId, derived.operation, {
          maxNativeCost: feePolicy.maxNativeCost,
          dailyNativeBudget: feePolicy.dailyNativeBudget,
          now: Date.now(),
        });
        if (reservation.replay) {
          writeJson(socket, { ok: true, replay: true, result: reservation.result });
          return;
        }
        // The adapter receives derived transaction fields only. It must not
        // accept transaction overrides from the caller.
        const result = await executeOperation({\n          transaction: derived, feePolicy, role,\n          onBroadcast: txHash => journal.markBroadcast(derived.authorizationId, derived.operation, txHash),\n        });
        assert(result && typeof result === "object" && typeof result.txHash === "string", "broadcast adapter returned no transaction hash");
        assert(typeof result.actualNativeCost === "string" && /^[0-9]+$/.test(result.actualNativeCost), "broadcast adapter returned no actual native cost");
        journal.complete(derived.authorizationId, derived.operation, result, result.actualNativeCost);
        writeJson(socket, { ok: true, replay: false, result });
      } catch (error) {
        // A failed adapter may have broadcast before failing. Keep reservation
        // unresolved: retries are blocked until explicit reconciliation.
        writeJson(socket, { ok: false, error: error?.message || "signer operation failed" });
      }
    });
  });

  return {
    server,
    async listen() {
      try {
        lstatSync(socketPath);
        throw new Error("socket path already exists; inspect the owning process before removing it");
      } catch (error) {
        if (error.code !== "ENOENT") throw error;
      }
      await new Promise((resolve, reject) => {
        server.once("error", reject);
        server.listen(socketPath, () => {
          server.removeListener("error", reject);
          resolve();
        });
      });
      chmodSync(socketPath, 0o660);
      return socketPath;
    },
    async close() {
      await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
      try { unlinkSync(socketPath); } catch (error) { if (error.code !== "ENOENT") throw error; }
    },
  };
}
