# Anna App — current release status

**Updated:** 2026-11-10  
**App:** verigate-authority · ID **851** · immutable Draft version **0.1.29** · version ID **2097**  
**Bundled Executa:** ID **1314** · version **0.1.16** · version ID **1042**

## Release state

- The immutable App 0.1.29 bundle is ready (3 files, 93,108 bytes); Anna Console confirms version ID **2097**.
- Anna platform state is **Draft**. The App is not Marketplace-published and has not been submitted for review.
- App 0.1.28 was a listing/metadata refresh over the App 0.1.27 runtime.
- App 0.1.27 introduced wallet lifecycle hardening: the UI reflects verified router consumption, clears stale authorization state on renewal, prevents duplicate issuance while a permission is active, and fails closed when a consume result is unknown.
- App 0.1.29 adds explicit ALLOW/WARN cancellation-state handling and regression coverage. It is cut as an immutable Draft, not released to end users.
- Bundled production Executa remains 0.1.16 (Executa ID 1314, version ID 1042); all four platform binaries were already cached and no new Executa version was created.

## What has been observed in Anna Runtime

Two distinct live Runtime recordings must be kept separate.

### 9 November — live MetaMask wallet hand-off

The user's recording `2026-11-09 15-05-43.mp4` demonstrates a real Anna Runtime session in Brave with the user's MetaMask extension:

1. Anna host Sampling interpreted a request to pay 25 USDC on Base to `0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed` for invoice 1042.
2. Verigate returned ALLOW and the App verified the Ed25519 Decision Receipt.
3. The App issued and verified a one-time Execution Authorization bound to that exact payment.
4. The user selected Send with connected wallet. The live MetaMask extension opened the exact 25 USDC Base transaction.
5. ExecutionRouter had already consumed the one-time permission before MetaMask asked for the signature. The App displayed that the permission was consumed and could not be retried.
6. The user denied the MetaMask signature. The App displayed `MetaMask Tx Signature: User denied transaction signature.`

**This is a successful live wallet hand-off and Router-consumption test, ending in an intentional user rejection at the wallet-signature step.** It proves that the real provider was available, the exact transaction reached MetaMask, and the consumed permission was not reusable. It does not prove a successful signature, transaction hash, broadcast or settlement.

The recording does not display an immutable App version identifier. Do not attribute it specifically to 0.1.29.

### 10 November — in-App cancellation regression

A separate recording shows the user deliberately cancelling the App's ALLOW/WARN permission confirmation. No App-scope approval was written and no Execution Authorization was created in that attempt. This cancellation path is covered by the 0.1.29 regression tests.

The earlier statement that no wallet was connected during the Anna Runtime tests was incorrect and is superseded by the 9 November MetaMask recording. The private source recording is documented in [the live MetaMask checkpoint](history/SESSION-CHECKPOINT-2026-11-10-LIVE-METAMASK.md).

## Automated and build evidence

- GitHub Actions Python unittest suite: **603 passed**.
- Anna UI E2E: **63/63 passed**, including ALLOW and WARN cancellation regression tests.
- Local targeted Anna Python suite rerun against the release checkout: **75 passed, 32 subtests passed**; strict schema-4 validation passed. These local checks do not prove live Cloud Agent or wallet execution.
- Exact-source CI for the App 0.1.27 lifecycle hardening and App 0.1.28 listing source: [run 42619825112](https://github.com/rudimentall1/verigate/actions/runs/42619825112), all three jobs passed.
- Four-platform Executa 0.1.16 reproducible build, packaging and extracted-package smoke tests: [run 42571400453](https://github.com/rudimentall1/verigate/actions/runs/42571400453). Windows x86_64, Linux x86_64, macOS ARM64 and macOS Intel x86_64 passed. These are workflow artifacts, not a public GitHub Release.
- App 0.1.29 source CI passed all three jobs: Python (603), Contracts, Anna UI (63/63), strict schema-4 validation and Linux Executa build/smoke: [run 42786256350](https://github.com/rudimentall1/verigate/actions/runs/42786256350). Anna Console subsequently cut immutable Draft version ID 2097; no release/publish action was taken.

## Remaining limits and release gates

- Availability and lifecycle persistence of an injected EIP-1193 provider in a fresh Anna Cloud Agent/Linux session remain unverified. The 9 November Brave + MetaMask live hand-off is proven separately; it must not be described as untested.
- Native USDC wallet hand-off is implemented for Base and Ethereum. Solana policy checks and signed authorizations exist, but Solana wallet submission is not included in this App.
- The 9 November recording ends with the user denying the MetaMask signature after ExecutionRouter consumed the one-time authorization. This intentionally burns that permission; a fresh policy check and new permission are required. The rolling 24-hour budget counts non-BLOCK authorization records, not chain-confirmed transfers.
- Accounting is scoped to one persistent Executa installation. Separate Cloud Agent workspaces or issuer keys are not aggregated into one account-wide budget.
- The App gates the supported Verigate App/ExecutionRouter path. It is not a universal firewall for external wallets or actions that bypass that router.
- No independent third-party security audit, hosted multi-tenant service, production KMS/HSM custody or key-rotation service is shipped.

**Release rule:** do not describe this App as approved, published, or payment-successful until those states are independently verified in Anna and, for payment success, on-chain.

## Verification entry points

- [Anna App implementation and Runtime acceptance notes](../README.md)
- [Anna documentation index](README.md)
- [Live MetaMask integration checkpoint — 9 November evidence](history/SESSION-CHECKPOINT-2026-11-10-LIVE-METAMASK.md)
- [Historical release-gate record](history/RELEASE-GATE-2026-11-09.md)
- [Repository threat model](../../docs/threat-model.md)
- [Anna release CI](https://github.com/rudimentall1/verigate/actions)