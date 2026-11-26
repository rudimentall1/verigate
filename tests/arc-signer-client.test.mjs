import test from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:net";
import { mkdtempSync, rmSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createArcSignerClient } from "../integrations/arc-signer-client.mjs";

async function startServer(socketPath, handler) {
  const server = createServer(socket => {
    let input = "";
    socket.on("data", chunk => {
      input += chunk.toString("utf8");
      const newline = input.indexOf("\n");
      if (newline >= 0) {
        const request = JSON.parse(input.slice(0, newline));
        socket.end(JSON.stringify(handler(request)) + "\n");
      }
    });
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(socketPath, resolve);
  });
  chmodSync(socketPath, 0o600);
  return server;
}

test("Arc signer client exposes only typed register, consume and payment methods", async () => {
  const dir = mkdtempSync(join(tmpdir(), "verigate-signer-client-"));
  const socketPath = join(dir, "signer.sock");
  const seen = [];
  const server = await startServer(socketPath, request => {
    seen.push(request);
    return { ok: true, replay: false, result: { txHash: "0x123", actualNativeCost: "10" } };
  });
  const client = createArcSignerClient({ socketPath });
  const authorization = { algorithm: "Ed25519", payload: {}, signature: "test" };
  try {
    const register = await client.register(authorization);
    const consume = await client.consume(authorization);
    const payment = await client.payment(authorization);
    assert.deepEqual(seen.map(x => x.operation), ["register", "consume", "payment"]);
    for (const request of seen) {
      assert.deepEqual(Object.keys(request).sort(), ["authorization", "operation"]);
      assert.deepEqual(request.authorization, authorization);
    }
    assert.equal(register.result.txHash, "0x123");
    assert.equal(consume.result.txHash, "0x123");
    assert.equal(payment.result.txHash, "0x123");
    assert.equal(typeof client.sign, "undefined");
    assert.equal(typeof client.sendTransaction, "undefined");
  } finally {
    await new Promise(resolve => server.close(resolve));
    rmSync(dir, { recursive: true, force: true });
  }
});

test("Arc signer client propagates fail-closed server errors", async () => {
  const dir = mkdtempSync(join(tmpdir(), "verigate-signer-client-error-"));
  const socketPath = join(dir, "signer.sock");
  const server = await startServer(socketPath, () => ({ ok: false, error: "authorization expired" }));
  const client = createArcSignerClient({ socketPath });
  try {
    await assert.rejects(client.payment({ payload: {} }), /authorization expired/);
  } finally {
    await new Promise(resolve => server.close(resolve));
    rmSync(dir, { recursive: true, force: true });
  }
});
