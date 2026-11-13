/**
 * Typed client for one role-specific Arc signer Unix socket.
 * There is intentionally no generic sign/send method.
 */
import { createConnection } from "node:net";

const MAX_RESPONSE_BYTES = 64 * 1024;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

export function createArcSignerClient({ socketPath, timeoutMs = 15_000 }) {
  assert(typeof socketPath === "string" && socketPath.startsWith("/"), "socketPath must be an absolute Unix socket path");
  assert(Number.isSafeInteger(timeoutMs) && timeoutMs >= 1000 && timeoutMs <= 120_000, "timeoutMs must be between 1 and 120 seconds");

  function request(operation, authorization) {
    assert(authorization && typeof authorization === "object", "signed Verigate authorization is required");
    return new Promise((resolve, reject) => {
      const socket = createConnection(socketPath);
      let response = "";
      let settled = false;
      const finish = (error, value) => {
        if (settled) return;
        settled = true;
        socket.destroy();
        if (error) reject(error);
        else resolve(value);
      };
      socket.setTimeout(timeoutMs, () => finish(new Error("Arc signer socket request timed out")));
      socket.once("error", error => finish(new Error("Arc signer socket unavailable: " + error.message)));
      socket.on("data", chunk => {
        response += chunk.toString("utf8");
        if (Buffer.byteLength(response, "utf8") > MAX_RESPONSE_BYTES) {
          finish(new Error("Arc signer response exceeds 64 KiB"));
          return;
        }
        const newline = response.indexOf("\n");
        if (newline < 0) return;
        if (response.slice(newline + 1).trim() !== "") {
          finish(new Error("Arc signer returned multiple response frames"));
          return;
        }
        try {
          const payload = JSON.parse(response.slice(0, newline));
          if (payload?.ok !== true) throw new Error(payload?.error || "Arc signer rejected operation");
          assert(payload.result && typeof payload.result === "object", "Arc signer returned no operation result");
          finish(null, { replay: payload.replay === true, result: payload.result });
        } catch (error) {
          finish(error);
        }
      });
      socket.once("connect", () => {
        socket.end(JSON.stringify({ operation, authorization }) + "\n");
      });
    });
  }

  return Object.freeze({
    register: authorization => request("register", authorization),
    consume: authorization => request("consume", authorization),
    payment: authorization => request("payment", authorization),
  });
}
