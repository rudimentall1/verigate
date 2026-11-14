# Solana Branch Session Checkpoint

**Updated:** 2026-11-14  
**Repository:** `rudimentall1/verigate`  
**Branch:** `feature/solana-transaction-binding`  
**Branch HEAD:** `3fbef5d67460f8e7ab91d1cb2092dcde7defff06`  
**Pull request:** [#60 — Bind Solana execution to authorized native SOL transfers](https://github.com/rudimentall1/verigate/pull/60)  
**PR status:** Open, Draft, targets `main`.  
**Checkpoint purpose:** Resume Solana work from this exact point without repeating the completed Devnet transfer or confusing historical live evidence with the current branch head.

## 1. What is implemented

### Transaction parser and semantic binding

The Solana adapter deliberately supports one narrow transaction family:

- Legacy Solana transaction format only.
- Exactly one required Ed25519 signer, also the fee payer.
- Exactly three account keys: sender, recipient and System Program.
- Exactly one top-level System Program instruction.
- Only the System Program `Transfer` instruction, with a positive u64 lamport amount.
- Exactly two instruction accounts in sender/recipient order.
- Maximum serialized transaction size: 1,232 bytes.

Before authorization consumption or broadcast, the adapter verifies the Ed25519 signature over the exact serialized message and binds the parsed transaction to the signed ActionIntent:

- `metadata.solana_sender` equals the fee payer and signer.
- `target` equals the parsed recipient.
- `metadata.destination`, when present, equals the parsed recipient.
- `asset = SOL` and `action_type = native.transfer`.
- Lamports exactly match the authorized SOL amount at 1,000,000,000 lamports per SOL; sub-lamport precision is rejected.

Malformed, ambiguous, unsupported or mismatched artifacts fail closed. The original serialized transaction is passed to the broadcaster only after validation and authorization enforcement.

### Cluster identity and execution boundary

- Signed ActionIntent includes `metadata.solana_genesis_hash`.
- A live genesis-hash provider is required through `NetworkRegistry`.
- Cluster identity is checked before one-time authorization consumption and again immediately before broadcast.
- Missing provider/hash, malformed RPC response or genesis mismatch fails closed.
- Concrete Solana transaction artifacts are routed to the Solana adapter before generic adapters; malformed or ambiguous EVM/Solana artifacts do not fall through to generic execution.
- Router-mediated execution keeps nonce consumption under `ExecutionRouter` control.
- Post-consumption hooks require a one-shot permit bound to the SHA-256 digest of the complete canonical authorization envelope.
- Caller-owned authorization inputs are deep-copied at router, gate and direct adapter boundaries to prevent mutation/redirection between validation, nonce consumption, permit claim and side effects.
- Regression coverage includes sender/recipient/amount/signature mismatch, action mutation, permit replay, nonce redirection, post-validation mutation, generic-adapter bypass and Valta proxy authorization snapshot behavior.

The permit is an in-process API guard, not a Python sandbox. Arbitrary malicious code in the same process and custom trusted adapters remain outside this protection boundary.

### Demo and evidence

The live Devnet demo runs the policy and execution lifecycle:

- 0.001 SOL: ALLOW, broadcast, then receipt advanced SUBMITTED -> CONFIRMED.
- 0.02 SOL: BLOCK with `per_tx_cap_exceeded`, no execution authorization and zero broadcasts.
- ExecutionMonitor polls RPC confirmation and ExecutionRouter creates the terminal signed receipt.

## 2. Live Devnet proof already completed — do not repeat

The live transaction was executed on **2026-11-13** using tested code commit:

`f6ff6f8db32c1e2c55078cb874bb5dfd53800553`

Evidence:

- Cluster: Solana Devnet, `https://api.devnet.solana.com`.
- Sender: `9GaArQHbeG1PLre3T12yL66frQuJcdJWwmRKL8JYg28F`.
- Recipient: `Aow21CH2NQbm6P4Q2owPiMbFJMpLifmtkSeGqKnzwB1Y`.
- Transfer: 0.001 SOL = 1,000,000 lamports.
- Signature: `5QUhbFF7NGLtvP5u2jmmhrKfE7Jmm9hbLbE8CbmJjpkDFJECLZmu8Zdtp5VQM7EdiSfsMAFNGE37mU9TjhVBEV7`.
- Slot: `521752939`.
- Independent `getTransaction` at confirmed commitment returned the expected System Program transfer, matching sender/recipient, `meta.err = null`, and a 5,000-lamport network fee.
- A separate `getSignatureStatuses` query returned `confirmationStatus = finalized`, `err = null`, and the same transaction slot.
- [Solana Explorer transaction](https://explorer.solana.com/tx/5QUhbFF7NGLtvP5u2jmmhrKfE7Jmm9hbLbE8CbmJjpkDFJECLZmu8Zdtp5VQM7EdiSfsMAFNGE37mU9TjhVBEV7?cluster=devnet)

This is RPC-level Devnet verification, not a third-party audit. The BLOCK/no-broadcast path is supported by demo output; it is not a second on-chain transaction.

**Evidence boundary:** the live transaction was run on `f6ff6f8...`, not on the current PR HEAD `3fbef5d...`. Later hardening commits are covered by CI, but have not been independently live-tested on Devnet. Do not imply otherwise.

## 3. CI and test status at this checkpoint

Current PR HEAD: `3fbef5d67460f8e7ab91d1cb2092dcde7defff06`.

Two completed CI runs for this exact HEAD passed all four jobs:

- [CI run #43408674187](https://github.com/rudimentall1/verigate/actions/runs/43408674187): contracts, container, test, anna-ui all success.
- [CI run #43407129052](https://github.com/rudimentall1/verigate/actions/runs/43407129052): contracts, container, test, anna-ui all success.

The four targeted local Solana test modules passed **15/15 on earlier tested code commit** `f6ff6f8...`. This local result is not a test result on current HEAD. Current HEAD has the two full CI runs above; rerun the targeted Solana modules on current HEAD before making a fresh local-test claim.

## 4. Deliberate unsupported scope

Do not describe this as general Solana transaction support. The adapter currently rejects:

- Versioned/v0 messages and address lookup tables.
- SPL Token / Token-2022 and associated-token-account instructions.
- Multiple instructions or signers.
- Compute-budget, memo and durable nonce instructions.
- PDA/CPI-driven transfer semantics.
- Arbitrary programs and account layouts.

RPC preflight remains enabled. The adapter does not independently prove blockhash freshness or simulate arbitrary program effects. Cluster binding depends on the configured genesis-hash provider and broadcaster using the same trusted RPC endpoint; it does not prove RPC honesty.

## 5. Work still planned — priority order

### P0 — Close the evidence gap on current HEAD

1. Run the four targeted Solana test modules on exact HEAD `3fbef5d...`; record command, test count and result.
2. Re-read the current PR diff and verify that each security claim in the PR body is directly supported by implementation and tests.
3. Confirm the current CI links remain attached to the exact PR HEAD. Do not rewrite the live Devnet evidence as if it ran on current HEAD.
4. Check for new mentor/reviewer comments and resolve them before feature expansion.

### P1 — Finish the PR review package

1. Make the supported transaction grammar and fail-closed behavior easy for an external reviewer to reproduce.
2. Ensure the runbook clearly separates parser tests, mocked RPC tests, Devnet demo evidence and independent RPC confirmation.
3. Keep PR #60 in Draft until the current-head test pass and review are complete. Do not merge without explicit authorization.

### P2 — Only after P0/P1

1. Consider a separate, narrowly scoped transaction family only if there is a concrete integration need and a complete semantic-binding test matrix. SPL transfers are a possible future scope, not an assumed next task.
2. Do not add versioned transactions, ALTs, multiple instructions or arbitrary programs as a breadth exercise.
3. Do not repeat the funded Devnet transfer unless a code change materially affects transaction construction, signature verification, cluster binding or broadcast behavior.

## 6. Resume instructions for the next session

Start by checking out `feature/solana-transaction-binding` at or beyond `3fbef5d67460f8e7ab91d1cb2092dcde7defff06`.

First task: run the targeted Solana test modules on the exact current branch HEAD and inspect the PR diff. Do not start a new feature before closing this verification gap.

Useful references:

- PR: https://github.com/rudimentall1/verigate/pull/60
- Branch: https://github.com/rudimentall1/verigate/tree/feature/solana-transaction-binding
- Scope and runbook: [docs/solana-native-transfer-scope.md](solana-native-transfer-scope.md)
- Live transaction: https://explorer.solana.com/tx/5QUhbFF7NGLtvP5u2jmmhrKfE7Jmm9hbLbE8CbmJjpkDFJECLZmu8Zdtp5VQM7EdiSfsMAFNGE37mU9TjhVBEV7?cluster=devnet

**Do not change `main`, merge PR #60, or make another live transfer as part of checkpoint creation.**
