import test from "node:test";
import assert from "node:assert/strict";
import { keccak256 } from "ethers";
import { createArcEthersAdapter } from "../integrations/arc-ethers-signer-adapter.mjs";
import { ARC_CHAIN_ID } from "../integrations/arc-constrained-signer.mjs";

const SIGNER = "0x2222222222222222222222222222222222222222";
const ISSUER = "0x1111111111111111111111111111111111111111";
const REGISTRY = "0x4D09CdD490c1Ce48BCB6DA5c1A6Bf41E2f5e853D";
const REGISTRY_CODE = "0x60006000556001600055";
const HASH = "0x" + "ef".repeat(32);
const policy = {
  gasLimit: "100000", maxFeePerGas: "100", maxPriorityFeePerGas: "5",
  maxNativeCost: "10000000", dailyNativeBudget: "50000000",
};

function mocks(overrides = {}) {
  const sent = [];
  const provider = {
    getNetwork: async () => ({ chainId: BigInt(ARC_CHAIN_ID) }),
    getCode: async () => REGISTRY_CODE,
    call: async () => "0x" + "0".repeat(63) + "1",
    getFeeData: async () => ({ maxFeePerGas: 90n, maxPriorityFeePerGas: 2n }),
    estimateGas: async () => 50000n,
    getTransactionCount: async () => 7,
    ...overrides.provider,
  };
  const wallet = {
    getAddress: async () => SIGNER,
    sendTransaction: async tx => {
      sent.push(tx);
      return {
        hash: HASH,
        wait: async () => ({
          hash: HASH, status: 1, blockNumber: 123,
          gasUsed: 21000n, gasPrice: 3n,
        }),
      };
    },
    ...overrides.wallet,
  };
  return { provider, wallet, sent };
}

test("Arc ethers adapter pins chain and Registry code, then broadcasts only derived zero-value tx", async () => {
  const m = mocks();
  const adapter = await createArcEthersAdapter({
    provider: m.provider, wallet: m.wallet, registryAddress: REGISTRY, role: "agent", issuerAddress: ISSUER,
    expectedRegistryCodeHash: keccak256(REGISTRY_CODE), feePolicy: policy,
  });
  await assert.rejects(adapter.executeOperation({ transaction: { chainId: ARC_CHAIN_ID, to: REGISTRY, data: "0x1234", value: 0n }, onBroadcast: async () => {} }), /startup verification/);
  const info = await adapter.initialize();
  assert.equal(info.chainId, ARC_CHAIN_ID);
  const result = await adapter.executeOperation({
    transaction: { chainId: ARC_CHAIN_ID, to: REGISTRY, data: "0x1234", value: 0n },
    onBroadcast: async () => {},
  });
  assert.equal(result.txHash, HASH);
  assert.equal(result.actualNativeCost, "63000");
  assert.equal(m.sent.length, 1);
  assert.equal(m.sent[0].nonce, 7);
  assert.equal(m.sent[0].maxFeePerGas, 100n);
  assert.equal(m.sent[0].value, 0n);
});

test("Arc ethers adapter fails closed on chain, bytecode, fee and gas mismatches", async () => {
  const wrongChain = mocks({ provider: { getNetwork: async () => ({ chainId: 1n }) } });
  const a = await createArcEthersAdapter({
    provider: wrongChain.provider, wallet: wrongChain.wallet, registryAddress: REGISTRY, role: "agent", issuerAddress: ISSUER,
    expectedRegistryCodeHash: keccak256(REGISTRY_CODE), feePolicy: policy,
  });
  await assert.rejects(a.initialize(), /not Arc Mainnet/);

  const wrongCode = mocks({ provider: { getCode: async () => "0x6001" } });
  const b = await createArcEthersAdapter({
    provider: wrongCode.provider, wallet: wrongCode.wallet, registryAddress: REGISTRY, role: "agent", issuerAddress: ISSUER,
    expectedRegistryCodeHash: keccak256(REGISTRY_CODE), feePolicy: policy,
  });
  await assert.rejects(b.initialize(), /bytecode hash mismatch/);

  const highFee = mocks({ provider: { getFeeData: async () => ({ maxFeePerGas: 101n, maxPriorityFeePerGas: 2n }) } });
  const c = await createArcEthersAdapter({
    provider: highFee.provider, wallet: highFee.wallet, registryAddress: REGISTRY, role: "agent", issuerAddress: ISSUER,
    expectedRegistryCodeHash: keccak256(REGISTRY_CODE), feePolicy: policy,
  });
  await c.initialize();
  await assert.rejects(c.executeOperation({ transaction: { chainId: ARC_CHAIN_ID, to: REGISTRY, data: "0x1234", value: 0n }, onBroadcast: async () => {} }), /exceeds signer policy/);

  const highGas = mocks({ provider: { estimateGas: async () => 100001n } });
  const d = await createArcEthersAdapter({
    provider: highGas.provider, wallet: highGas.wallet, registryAddress: REGISTRY, role: "agent", issuerAddress: ISSUER,
    expectedRegistryCodeHash: keccak256(REGISTRY_CODE), feePolicy: policy,
  });
  await d.initialize();
  await assert.rejects(d.executeOperation({ transaction: { chainId: ARC_CHAIN_ID, to: REGISTRY, data: "0x1234", value: 0n }, onBroadcast: async () => {} }), /estimated gas exceeds/);
});

test("Arc adapter rejects a disabled issuer and an issuer key/address mismatch", async () => {
  const disabled = mocks({ provider: { call: async () => "0x" + "0".repeat(64) } });
  const a = await createArcEthersAdapter({
    provider: disabled.provider, wallet: disabled.wallet, registryAddress: REGISTRY,
    role: "agent", issuerAddress: ISSUER,
    expectedRegistryCodeHash: keccak256(REGISTRY_CODE), feePolicy: policy,
  });
  await assert.rejects(a.initialize(), /issuer is not enabled/);

  const mismatch = mocks();
  const b = await createArcEthersAdapter({
    provider: mismatch.provider, wallet: mismatch.wallet, registryAddress: REGISTRY,
    role: "issuer", issuerAddress: ISSUER,
    expectedRegistryCodeHash: keccak256(REGISTRY_CODE), feePolicy: policy,
  });
  await assert.rejects(b.initialize(), /issuer signer address differs/);
});

test("Arc agent signer cannot reuse the Registry issuer address", async () => {
  const sameAddress = mocks({ wallet: { getAddress: async () => ISSUER } });
  const adapter = await createArcEthersAdapter({
    provider: sameAddress.provider, wallet: sameAddress.wallet, registryAddress: REGISTRY,
    role: "agent", issuerAddress: ISSUER,
    expectedRegistryCodeHash: keccak256(REGISTRY_CODE), feePolicy: policy,
  });
  await assert.rejects(adapter.initialize(), /distinct address from the Registry issuer/);
});
