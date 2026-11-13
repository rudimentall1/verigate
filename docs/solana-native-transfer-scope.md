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

## Remaining proof work

The current unit tests exercise parsing, signature verification, and sender,
recipient, amount, and replay mismatches using locally generated signed
transactions. They do not constitute a live Devnet verification.

The live demo still uses a directly constructed ALLOW decision. A subsequent
integration step must route the intent through the configured policy engine,
demonstrate a policy BLOCK with zero RPC broadcasts, and independently verify
the successful Devnet transaction and execution receipt.

The RPC preflight remains enabled on broadcast. This adapter does not itself
prove blockhash freshness or simulate arbitrary program effects.
