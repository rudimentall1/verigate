# Anna App — current release status

**Updated:** 2026-11-09  
**App:** verigate-authority · ID **851** · version **0.1.28** · version ID **2082**  
**Bundled Executa:** ID **1314** · version **0.1.16** · version ID **1042**

## Release state

- The immutable App 0.1.28 bundle is ready (3 files, 91,055 bytes).
- Anna platform state is **Draft**. The App is not Marketplace-published and has not been submitted for review.
- App 0.1.28 is a listing/metadata refresh. It carries forward the App 0.1.27 runtime without changing policy or wallet behavior.
- App 0.1.27 introduced wallet lifecycle hardening: the UI reflects verified router consumption, clears stale authorization state on renewal, prevents duplicate issuance while a permission is active, and fails closed when a consume result is unknown.
- Bundled production Executa remains 0.1.16. App 0.1.28 did not publish or replace the Executa.

## What has been observed in Anna Runtime

The reviewed recordings from 9–10 November demonstrate the Anna interpretation and policy-preview path:

1. Anna host Sampling interpreted natural-language payment requests and returned contextual risk findings.
2. Verigate returned deterministic ALLOW, BLOCK and WARN decisions.
3. The App verified Ed25519-signed Decision Receipts before displaying results.
4. A prompt-injection request escalated to WARN with `prompt_injection` and `urgency_pressure` flags.
5. The App displayed the explicit payment/warning confirmation dialog. In the 10 November recording, the user deliberately selected Cancel; no App-scope approval was written and no permission was created in that attempt.

**No wallet was connected in these tests.** No live ExecutionRouter consumption, wallet signature, transaction hash, broadcast, on-chain inclusion or settlement is claimed. Earlier text in this file describing MetaMask display and router consumption was inaccurate and is withdrawn.

The 10 November recording does not display an immutable App version identifier. It therefore does not establish live Runtime acceptance of App 0.1.28. App 0.1.28 remains the Draft listing refresh described above; its runtime is inherited from 0.1.27.

## Automated and build evidence

- Full Python suite: **626 passed, 4 skipped**.
- Anna UI E2E: **61/61 passed**.
- Exact-source CI for the App 0.1.27 lifecycle hardening and App 0.1.28 listing source: [run 42619825112](https://github.com/rudimentall1/verigate/actions/runs/42619825112), all three jobs passed.
- Four-platform Executa 0.1.16 reproducible build, packaging and extracted-package smoke tests: [run 42571400453](https://github.com/rudimentall1/verigate/actions/runs/42571400453). Windows x86_64, Linux x86_64, macOS ARM64 and macOS Intel x86_64 passed. These are workflow artifacts, not a public GitHub Release.

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