# Anna live MetaMask integration checkpoint

**Checkpoint date:** 2026-11-10  
**Evidence date:** 2026-11-09  
**Product:** Verigate Authority Anna App

## Mandatory correction to project history

The statement that no wallet was connected during the Anna Runtime tests is false and must not be repeated.

The user supplied a screen recording on 9 November 2026 showing the real Anna Runtime running in Brave with the user's MetaMask extension. The recording demonstrates a live EIP-1193 wallet hand-off through Verigate ExecutionRouter up to the wallet signature request. This is not the mocked EIP-1193 provider used by automated UI tests.

The exact immutable Anna App version identifier is not visible in that recording. Do not attribute it specifically to App 0.1.28 or 0.1.29 without separate platform evidence.

## Source recording

- Private user-supplied recording: `2026-11-09 15-05-43.mp4`
- Resolution / frame rate: 1920×1080 at 30 fps
- Duration: 735.667 seconds (12:15.667)
- The Windows taskbar in the relevant frames displays 09.11.2026 around 15:16.
- SHA-256: `3b349caabc26b7ba106bca591f9c3c917b987cdea5bee9f8090e310f1659c6d8`
- The original video remains in the user's private ChatGPT file library; it is not copied into this public repository.

## What the recording proves

The live request shown in the Anna App was:

- Amount: **25 USDC**
- Network: **Base**
- Recipient: `0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed`
- Purpose: **invoice 1042**

Observed sequence:

1. Anna's host LLM interpreted the natural-language payment request and returned contextual risk analysis.
2. Verigate returned **ALLOW** under deterministic policy.
3. The App displayed the Ed25519-signed Decision Receipt and showed that its signature was verified.
4. The App created a one-time Execution Authorization bound to the exact 25 USDC Base payment. The permission was verified in the UI.
5. The user selected **Send with connected wallet**. The App used the injected wallet provider in the Brave browser.
6. Verigate ExecutionRouter consumed the one-time permission before the external wallet signature request. The App displayed: **“Permission consumed. No retry is possible with this authorization.”**
7. The real MetaMask extension opened a transaction confirmation for **25 USDC**, from **Wallet 1**, on **Base**, to the intended recipient.
8. The user denied the MetaMask signature. The App displayed the exact error: **“MetaMask Tx Signature: User denied transaction signature.”**

The relevant end frame therefore proves the refusal path after real MetaMask hand-off, not a successful payment.

## Evidence classification

| Check | Result | Evidence boundary |
|---|---|---|
| Anna LLM interpretation | PASS | Visible in the live Anna Runtime recording |
| Deterministic ALLOW decision | PASS | Visible in the App |
| Decision Receipt verification | PASS | App displays successful Ed25519 verification |
| One-time Execution Authorization | PASS | Permission displayed and verified |
| ExecutionRouter one-time consumption | PASS | App displays consumed state before wallet signature |
| Injected EIP-1193 provider | PASS | Real MetaMask extension is opened from the Brave session |
| Exact wallet transaction hand-off | PASS | MetaMask shows 25 USDC on Base and the intended recipient |
| User-denied wallet signature handling | PASS | App shows the denial and does not offer reuse of the consumed authorization |
| Wallet signature accepted | NOT DEMONSTRATED | User denied the signature request |
| Transaction hash returned | NOT DEMONSTRATED | No hash is shown in the recording |
| Transaction broadcast / on-chain inclusion | NOT DEMONSTRATED | No broadcast, receipt, block inclusion or settlement is shown |

**Correct summary:** live MetaMask wallet hand-off and ExecutionRouter consumption were tested successfully through the actual wallet confirmation screen. The user deliberately rejected the wallet signature. No payment was submitted or settled in this recorded attempt.

This is a meaningful live end-to-end negative-path test. It verifies that ExecutionRouter consumes the authorization before the wallet prompt and that a wallet rejection is surfaced without making the old authorization retryable. It must not be downgraded to “wallet never connected”, and it must not be inflated into “payment succeeded”.

## Separate 10 November cancellation recording

A different 10 November Runtime recording shows the user deliberately cancelling the in-App permission confirmation. That attempt correctly writes no App-scope approval and creates no Execution Authorization. It is a separate test from the 9 November MetaMask test.

## Current platform release state (verified 2026-11-10)

- Anna App ID: **851**
- Latest immutable App version: **0.1.29**, version ID **2097**
- Platform status: **Draft**; not Marketplace-published and not submitted for review
- Bundle: **ready**, 3 files, 93,108 bytes
- Bundled Executa: ID **1314**, version **0.1.16**, version ID **1042**
- App 0.1.29 was cut after the 9 November MetaMask recording. The recording does not identify its immutable App version and must not be presented as proof that 0.1.29 itself has passed live wallet acceptance.

## Automated verification on 10 November

- Anna UI E2E: **63/63 passed**
- Targeted Anna Python suite: **75 passed, 32 subtests passed**
- Anna schema-4 strict validation: **passed**
- App 0.1.29 source CI: [run 42786256350](https://github.com/rudimentall1/verigate/actions/runs/42786256350) — Python, Contracts and Anna UI jobs passed
- The automated wallet tests use a mocked EIP-1193 provider. They complement, but do not replace, the real MetaMask recording above.

## What remains unverified

1. Re-run acceptance against the installed immutable App **0.1.29** so the live result is tied to that exact platform version.
2. Availability and lifecycle persistence of the injected wallet provider in a fresh Anna Cloud Agent/Linux session.
3. A user-approved MetaMask signature, wallet-returned transaction hash and the resulting `SUBMITTED` receipt.
4. Independent chain verification of transaction inclusion, confirmation depth, finality and reorg status.
5. Cloud Agent storage persistence across restart/reinstall and replay rejection against the live App-scope store.

No further wallet test should be described as a first-time MetaMask integration. The first live MetaMask hand-off and Router-consume test already exists in the 9 November recording. Any new test is a version-specific regression test or a separately authorized positive-signature / chain-settlement test.

## Operating rule for future assistants and contributors

- Treat this file as the authoritative correction to any earlier note saying no wallet was connected.
- Never ask the user to repeat the already-recorded 9 November MetaMask hand-off just to prove that a wallet exists.
- Distinguish the real MetaMask recording from the mocked EIP-1193 test harness.
- Distinguish Router consumption from wallet signature, transaction broadcast and chain settlement.
- Do not claim an on-chain payment without the actual transaction hash and independent chain verification.
- Do not release or submit App 0.1.29 merely because these tests pass; review and release are separate platform lifecycle actions.
