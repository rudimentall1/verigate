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

The reviewed recordings from 9–10 November demonstrate the Anna interpretation and policy-preview path:

1. Anna host Sampling interpreted natural-language payment requests and returned contextual risk findings.
2. Verigate returned deterministic ALLOW, BLOCK and WARN decisions.
3. The App verified Ed25519-signed Decision Receipts before displaying results.
4. A prompt-injection request escalated to WARN with `prompt_injection` and `urgency_pressure` flags.
5. The App displayed the explicit payment/warning confirmation dialog. In the 10 November recording, the user deliberately selected Cancel; no App-scope approval was written and no permission was created in that attempt.

**No wallet was connected in these tests.** No live ExecutionRouter consumption, wallet signature, transaction hash, broadcast, on-chain inclusion or settlement is claimed. Earlier text in this file describing MetaMask display and router consumption was inaccurate and is withdrawn.

The 10 November recording does not display an immutable App version identifier. It therefore does not establish live Runtime acceptance of App 0.1.29. The recording predates the 0.1.29 cut and remains evidence only for the interpretation and policy-preview path.

## Automated and build evidence

- GitHub Actions Python unittest suite: **603 passed**.
- Anna UI E2E: **63/63 passed**, including ALLOW and WARN cancellation regression tests.
- Local targeted Anna Python suite rerun against the release checkout: **75 passed, 32 subtests passed**; strict schema-4 validation passed. These local checks do not prove live Cloud Agent or wallet execution.
- Exact-source CI for the App 0.1.27 lifecycle hardening and App 0.1.28 listing source: [run 42619825112](https://github.com/rudimentall1/verigate/actions/runs/42619825112), all three jobs passed.
- Four-platform Executa 0.1.16 reproducible build, packaging and extracted-package smoke tests: [run 42571400453](https://github.com/rudimentall1/verigate/actions/runs/42571400453). Windows x86_64, Linux x86_64, macOS ARM64 and macOS Intel x86_64 passed. These are workflow artifacts, not a public GitHub Release.
- App 0.1.29 source CI passed all three jobs: Python (603), Contracts, Anna UI (63/63), strict schema-4 validation and Linux Executa build/smoke: [run 42786256350](https://github.com/rudimentall1/verigate/actions/runs/42786256350). Anna Console subsequently cut immutable Draft version ID 2097; no release/publish action was taken.

## Remaining limits and release gates

- Availability of an injected EIP-1193 wallet provider in a fresh Anna Cloud Agent session remains unverified. Cloud persistence across restart/reinstall also remains unverified.
- Native USDC wallet hand-off is implemented for Base and Ethereum. Solana policy checks and signed authorizations exist, but Solana wallet submission is not included in this App.
- The rolling 24-hour budget counts non-BLOCK authorization records, not chain-confirmed transfers. A cancelled or rejected wallet prompt does not automatically release the reservation.
- Accounting is scoped to one persistent Executa installation. Separate Cloud Agent workspaces or issuer keys are not aggregated into one account-wide budget.
- The App gates the supported Verigate App/ExecutionRouter path. It is not a universal firewall for external wallets or actions that bypass that router.
- No independent third-party security audit, hosted multi-tenant service, production KMS/HSM custody or key-rotation service is shipped.

**Release rule:** do not describe this App as approved, published, or payment-successful until those states are independently verified in Anna and, for payment success, on-chain.

## Verification entry points

- [Anna App implementation and Runtime acceptance notes](../README.md)
- [Anna documentation index](README.md)
- [Historical release-gate record](history/RELEASE-GATE-2026-11-09.md)
- [Repository threat model](../../docs/threat-model.md)
- [Anna release CI](https://github.com/rudimentall1/verigate/actions)