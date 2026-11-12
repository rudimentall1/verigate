#!/usr/bin/env node
/**
 * Read-only Arc Mainnet receipt sampling for the Registry lifecycle.
 * Reports native USDC gas costs in their canonical 18-decimal units.
 * This script never signs or broadcasts a transaction.
 */
import { JsonRpcProvider, formatUnits } from "ethers";

const RPC_URL = process.env.VERIGATE_ARC_RPC_URL || "https://rpc.mainnet.arc.io";
const samples = [
  { operation: "register-authorization-1", hash: "0xa6a2fb23af073085c64bb168f14ee02d90d64fbeb4629dc2724ba1d01624867f" },
  { operation: "register-authorization-2", hash: "0x5f45d89e0f12e42a0d00268d6125a2b05f6474f4ed786895bc7715cf39ad1696" },
  { operation: "consume-authorization", hash: "0xc0b2a5de7973da979808ebf5f69e4736ad1eea22fc1fdd5f698b2b44cbad5de8" },
];

const provider = new JsonRpcProvider(RPC_URL, 5042, { staticNetwork: true });
try {
  const network = await provider.getNetwork();
  if (network.chainId !== 5042n) throw new Error(`Expected Arc Mainnet 5042, got ${network.chainId}`);
  const results = [];
  for (const sample of samples) {
    const receipt = await provider.send("eth_getTransactionReceipt", [sample.hash]);
    if (!receipt) throw new Error(`Arc RPC did not return a receipt for ${sample.operation} (${sample.hash})`);
    if (String(receipt.transactionHash).toLowerCase() !== sample.hash.toLowerCase()) {
      throw new Error(`Receipt transaction hash mismatch for ${sample.operation}`);
    }
    if (BigInt(receipt.status) !== 1n) throw new Error(`${sample.operation} did not succeed on Arc`);
    const gasUsed = BigInt(receipt.gasUsed);
    const effectiveGasPrice = receipt.effectiveGasPrice == null ? null : BigInt(receipt.effectiveGasPrice);
    if (gasUsed <= 0n || effectiveGasPrice == null || effectiveGasPrice <= 0n) {
      throw new Error(`Receipt lacks valid gasUsed/effectiveGasPrice for ${sample.operation}`);
    }
    const nativeFee18 = gasUsed * effectiveGasPrice;
    const erc20Fee6 = nativeFee18 / 10n ** 12n;
    const precisionRemainder = nativeFee18 % 10n ** 12n;
    results.push({
      operation: sample.operation,
      transactionHash: sample.hash,
      blockNumber: Number(BigInt(receipt.blockNumber)),
      from: receipt.from,
      to: receipt.to,
      status: "success",
      gasUsed: gasUsed.toString(),
      effectiveGasPriceWei: effectiveGasPrice.toString(),
      nativeUsdcFee18: nativeFee18.toString(),
      nativeUsdcFee: formatUnits(nativeFee18, 18),
      erc20SixDecimalEquivalent: formatUnits(erc20Fee6, 6),
      subMicroNativeRemainder: precisionRemainder.toString(),
    });
  }
  const maximum = results.reduce((best, item) => BigInt(item.nativeUsdcFee18) > BigInt(best.nativeUsdcFee18) ? item : best);
  process.stdout.write(JSON.stringify({
    result: "PASS",
    chainId: 5042,
    feeAsset: "native USDC",
    nativeDecimals: 18,
    erc20Decimals: 6,
    conversionFactor: "1000000000000",
    samples: results,
    maximumSample: { operation: maximum.operation, nativeUsdcFee18: maximum.nativeUsdcFee18, nativeUsdcFee: maximum.nativeUsdcFee },
    note: "Historical receipt samples only. They inform fee ceilings but do not set or approve production limits.",
  }, null, 2) + "\n");
} finally {
  await provider.destroy();
}
