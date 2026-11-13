# Solana native-transfer execution boundary

## Implemented scope

The Solana execution adapter accepts only a deliberately narrow transaction
shape:

- legacy message format (no version prefix);
- exactly one required Ed25519 signer, who is also the fee payer;
- exactly three account keys: sender, recipient, System Program;
- exactly one top-level System Program instruction;
- instruction data is the System Program `Transfer` opcode (2) with a positive
  u64 lamport amount;
- exactly two instruction accounts in sender/recipient order;
- transaction size does not exceed 1,232 bytes.

Before authorization is consumed or a broadcaster is called, Verigate verifies
the sender's Ed25519 signature over the exact serialized message and binds the
decoded transaction to the signed ActionIntent:

- `metadata.solana_sender` must equal the fee payer and signer;
- `target` must equal the transaction recipient;
- `metadata.destination`, when present, must equal the transaction recipient;
- `asset` must be `SOL`;
- `action_type` must be `native.transfer`;
- the instruction's lamports must exactly equal the authorized SOL amount,
  converted at 1,000,000,000 lamports per SOL with no sub-lamport precision.

Any malformed, ambiguous, unsupported, or mismatched transaction fails closed.
The original serialized transaction is passed unchanged to the RPC broadcaster
only after these checks and the existing one-time execution authorization gate.

## Explicitly unsupported

This is not yet a general Solana transaction parser. It rejects:

- v0/versioned messages and address lookup tables;
- multiple signers or multiple instructions;
- SPL Token / Token-2022 transfers, associated-token-account instructions;
- compute-budget instructions, memo instructions, durable nonce flows;
- program-derived-address or CPI-driven transfer semantics;
- arbitrary programs and account layouts.

These are intentionally rejected rather than treated as safe. Support should be
added one transaction family at a time, with dedicated semantic binding and
negative tests.

## Reproduce the live Devnet proof

Run from the repository root in an environment where the project's Python
dependencies are installed:

```bash
python demo_live_solana_devnet.py
```

By default, the demo creates temporary Devnet-only keys, requests a 1 SOL
Devnet faucet airdrop, and transfers 0.001 SOL to a newly generated recipient.
The sender needs at least 0.0011 SOL. Faucet availability and rate limits are
external dependencies; a faucet failure is not evidence of an adapter failure.

To use an already-funded Devnet CLI keypair instead:

```bash
python demo_live_solana_devnet.py --sender-keypair /absolute/path/to/devnet-keypair.json --skip-airdrop
```

On PowerShell, set a custom RPC endpoint only if needed:

```powershell
$env:VERIGATE_SOLANA_DEVNET_RPC_URL = "https://api.devnet.solana.com"
python .\demo_live_solana_devnet.py
```

The keypair file is read locally and must never be committed or pasted into
chat, logs, issues, or pull requests. The demo does not print the private key.
It uses a temporary directory for Verigate's issuer key and audit database.

Expected evidence includes:
- small transfer policy result: `ALLOW`;
- oversized transfer policy result: `BLOCK`;
- blocked transfer execution authorization: `NONE`;
- blocked transfer broadcasts: `0`;
- successful transfer receipt: `CONFIRMED`;
- transaction signature and Devnet Explorer URL.

Verify the signature independently in Solana Explorer with the Devnet cluster
selected, and query `getSignatureStatuses` against the configured Devnet RPC.
Record the transaction signature, slot, RPC response, and run timestamp in the
PR evidence. Do not describe the integration as live-tested until this run
completes and the transaction is independently confirmed.

## Verification status

The targeted local Solana test modules passed 15/15 on tested code commit
`f6ff6f8db32c1e2c55078cb874bb5dfd53800553`.

A live Devnet run and two separate read-only RPC lookups are recorded below.
`getTransaction` verified transaction contents at `confirmed` commitment;
`getSignatureStatuses` subsequently returned `finalized` with `err = null`.
This is RPC-level Devnet verification, not a third-party audit.

The BLOCK/no-broadcast path is evidenced by the demo output and its execution
guard; it is not represented as an on-chain transaction.

The RPC preflight remains enabled on broadcast. This adapter does not itself
prove blockhash freshness or simulate arbitrary program effects.


## Recorded live Devnet evidence

Run completed on 2026-11-13 at 07:44:32 UTC (RPC blockTime).

- Tested code commit: `f6ff6f8db32c1e2c55078cb874bb5dfd53800553`.
- Network: Solana Devnet (`https://api.devnet.solana.com`).
- Sender: `9GaArQHbeG1PLre3T12yL66frQuJcdJWwmRKL8JYg28F`.
- Recipient: `Aow21CH2NQbm6P4Q2owPiMbFJMpLifmtkSeGqKnzwB1Y`.
- Policy: 0.001 SOL `ALLOW`; 0.02 SOL `BLOCK` with rule `per_tx_cap_exceeded`.
- Blocked path: no execution authorization; zero broadcasts.
- Allowed path: broadcast returned `SUBMITTED`, then `CONFIRMED`.
- Signature: `5QUhbFF7NGLtv5P2u2jmmhrKfE7Jmm9hbLbE8CbmJjpkDFJECLZmu8Zdtp5VQM7EdiSfsMAFNGE37mU9TjhVBEV7`.
- Slot: `521752939`.
- Independent read-only `getTransaction` response at commitment `confirmed`: transaction found; `meta.err = null`; System Program `transfer`; source and destination match; amount is 1,000,000 lamports (0.001 SOL); fee is 5,000 lamports (0.000005 SOL).
- Independent read-only `getSignatureStatuses` response: `confirmationStatus = finalized`; `err = null`; `status = {"Ok": null}`; transaction slot `521752939`; RPC context slot `521754267`.
- Explorer: https://explorer.solana.com/tx/5QUhbFF7NGLtv5P2u2jmmhrKfE7Jmm9hbLbE8CbmJjpkDFJECLZmu8Zdtp5VQM7EdiSfsMAFNGE37mU9TjhVBEV7?cluster=devnet

The demo result and separate RPC lookups agree. The live Devnet transaction contents were independently checked at `confirmed` commitment, and a subsequent signature-status query returned `finalized` with no execution error. This is independent RPC verification, not a third-party audit. The oversized BLOCK/no-broadcast result is established by the demo's execution output; it is not a second on-chain transaction.
