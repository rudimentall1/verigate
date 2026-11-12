#!/usr/bin/env node
/**
 * Read-only Arc Mainnet receipt sampling for the Registry lifecycle.
 * Reports native USDC gas costs in their canonical 18-decimal units.
 * This script never signs or broadcasts a transaction.
 */
import { JsonRpcProvider, formatUnits } from "ethers";

const RPC_URL = process.env.VERIGATE_ARC_RPC_URL || "https://rpc.mainnet.arc.io";
const samples = [
  { operation: "register-authorization-1", evidenceClass: "Verigate Registry history", to: "0x4D09CdD490c1Ce48BCB6DA5c1A6Bf41E2f5e853D", selector: "0xb267748a", hash: "0xa6a2fb23af073085c64bb168f14ee02d90d64fbeb4629dc2724ba1d01624867f" },
  { operation: "register-authorization-2", evidenceClass: "Verigate Registry history", to: "0x4D09CdD490c1Ce48BCB6DA5c1A6Bf41E2f5e853D", selector: "0xb267748a", hash: "0x5f45d89e0f12e42a0d00268d6125a2b05f6474f4ed786895bc7715cf39ad1696" },
  { operation: "consume-authorization", evidenceClass: "Verigate Registry history", to: "0x4D09CdD490c1Ce48BCB6DA5c1A6Bf41E2f5e853D", selector: "0xbad56b75", hash: "0xc0b2a5de7973da979808ebf5f69e4736ad1eea22fc1fdd5f698b2b44cbad5de8" },
  { operation: "erc20-usdc-transfer-reference", evidenceClass: "separate Agentic Wallet Guardian v3 project; fee reference only, not Verigate payment evidence", to: "0x3600000000000000000000000000000000000000", selector: "0xa9059cbb", hash: "0xd781e8b04b5ca89c3a34fcec50a6636049f7647d2b0e1b2bb64d5b1ee54daadf" },
];

const provider = new JsonRpcProvider(RPC_URL, 5042, { staticNetwork: true });
let archiveProvider = null;
let archiveVerified = false;
try {
  const network = await provider.getNetwork();
  if (network.chainId !== 5042n) throw new Error(`Expected Arc Mainnet 5042, got ${network.chainId}`);
  const results = [];
  for (const sample of samples) {
    let source = "primary Arc RPC";
    let tx = await provider.getTransaction(sample.hash);
    let receipt = await provider.send("eth_getTransactionReceipt", [sample.hash]);
    if (!tx || !receipt) {
      // Arc RPC nodes may prune old hash/receipt lookups. Arcscan documents
      // its read-only RPC as a multi-provider fallback for historical reads.
      archiveProvider ??= new JsonRpcProvider("https://rpc.arc-scan.org", 5042, { staticNetwork: true });
      if (!archiveVerified) {
        const archiveChainId = BigInt(await archiveProvider.send("eth_chainId", []));
        if (archiveChainId !== 5042n) throw new Error(`Arcscan fallback RPC returned chain ${archiveChainId}, expected 5042`);
        archiveVerified = true;
      }
      tx ??= await archiveProvider.getTransaction(sample.hash);
      receipt ??= await archiveProvider.send("eth_getTransactionReceipt", [sample.hash]);
      source = "Arcscan read-only RPC fallback";
    }
    const transaction = tx;
    if (!transaction) throw new Error(`No transaction data from primary or archive RPC for ${sample.operation} (${sample.hash})`);
    if (!receipt) throw new Error(`No receipt from primary or archive RPC for ${sample.operation} (${sample.hash})`);
    if (String(transaction.to).toLowerCase() !== sample.to.toLowerCase()) {
      throw new Error(`Transaction destination mismatch for ${sample.operation}`);
    }
    if (String(transaction.data).slice(0, 10).toLowerCase() !== sample.selector) {
      throw new Error(`Transaction selector mismatch for ${sample.operation}`);
    }
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
      evidenceClass: sample.evidenceClass,
      rpcSource: source,
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
  if (archiveProvider) await archiveProvider.destroy();
}
