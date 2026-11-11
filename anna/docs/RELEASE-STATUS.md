# Anna App — current release status

**Updated:** 2026-11-11  
**Repository source candidate:** commit `6eca3bd782fe54ca798ac3fd66a54acde61b41fc` on `main`  
**Source candidate:** Anna App **0.1.30** · bundled Executa **0.1.17**  
**Last recorded Anna Console state (10 November):** immutable Draft App **0.1.29** · version ID **2097** · App ID **851**; bundled Executa **0.1.16** · version ID **1042** · Executa ID **1314**

## Current source candidate — 11 November

PR [#44](https://github.com/rudimentall1/verigate/pull/44) is merged into `main`. Its source candidate is App 0.1.30 / Executa 0.1.17. The source manifest requires bundled Executa >= 0.1.17.

The source candidate is **not** an immutable Anna Console version. The last recorded Console snapshot remains the 0.1.29 / 0.1.16 Draft above. Do not claim that 0.1.30 / 0.1.17 is uploaded, cut, approved, Marketplace-published or installed in a Cloud Agent.

### Exact-source main CI

[GitHub Actions run 42874904974](https://github.com/rudimentall1/verigate/actions/runs/42874904974) ran on the merged `main` commit and completed successfully. All three jobs passed:

- Python unittest suite: **613 tests passed**; demo and API app smoke checks passed.
- Anna UI: strict schema-4 validation passed; **64/64 UI flow tests passed**.
- Contracts: atomic-state end-to-end and access-control tests passed.
- Linux Executa 0.1.17 was built, packaged, extracted and smoke-tested. The log records a successful `describe`, ALLOW decision, signed receipt, one-time App-scope approval consumption, one-time wallet-handoff consumption, and persisted/verified SUBMITTED receipt.

This proves the merged source and the Linux CI path. It does not prove a fresh Anna Cloud Agent installation, a live invocation in Anna, or a successful on-chain payment.

### Executa 0.1.17 platform packages

The repository workflow `.github/workflows/anna-executa-binaries.yml` defines four build targets: Linux x86_64, Windows x86_64, macOS ARM64 and macOS Intel x86_64. **A four-platform 0.1.17 workflow run and its extracted-package smoke tests have not been evidenced.** The successful run above only builds and smoke-tests Linux x86_64.

The newest GitHub Release observed on 11 November is still the draft Executa **0.1.14**. No 0.1.17 release or four-platform 0.1.17 asset set was present in the Releases listing. Do not reuse 0.1.14 or 0.1.16 binaries as evidence for 0.1.17.

For a non-publishing matrix build, manually dispatch `Anna Executa Binaries` with version `0.1.17` and `publish_release=false`. This builds and smoke-tests all four targets and uploads workflow artifacts; it does not publish a GitHub Release. Keep `publish_release=false` until the artifacts have been inspected and a separate release decision is made.

## Anna Console state

The last recorded Console inspection on 10 November confirmed:

- App ID **851**, immutable Draft version **0.1.29**, version ID **2097**.
- Bundled Executa ID **1314**, version **0.1.16**, version ID **1042**.
- The App was in **Draft** state, not Marketplace-published and not submitted for review.

This snapshot predates PR #44. Recheck the Console before changing or cutting any immutable version. Do not overwrite or remove the existing Draft as part of source-level work.

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

The recording does not display an immutable App version identifier. Do not attribute it specifically to 0.1.29 or 0.1.30.

### 10 November — in-App cancellation regression

A separate recording shows the user deliberately cancelling the App's ALLOW/WARN permission confirmation. No App-scope approval was written and no Execution Authorization was created in that attempt. This cancellation path is covered by the UI regression tests.

The earlier statement that no wallet was connected during the Anna Runtime tests was incorrect and is superseded by the 9 November MetaMask recording. The private source recording is documented in [the live MetaMask checkpoint](history/SESSION-CHECKPOINT-2026-11-10-LIVE-METAMASK.md).

## What PR #44 adds

App 0.1.30 / Executa 0.1.17 adds authorization-bound signed wallet outcome receipts and preserves Anna invoke correlation diagnostics:

- `REJECTED`: only EIP-1193 error 4001 during `eth_sendTransaction`.
- `ABORTED`: only a proven pre-wallet abort, or a lost Router response for which the durable nonce ledger proves that the exact authorization was consumed.
- `UNKNOWN`: the wallet request started, but the result is ambiguous and no valid transaction hash was returned.
- `SUBMITTED`: existing path retained when the wallet returns a transaction hash.

Negative receipts are signed by the Anna installation issuer and explicitly identified as executor self-reports, not wallet-signed evidence or independent chain confirmation. Each receipt is bound to the exact authorization and a fresh one-time App-scope approval. Ambiguous `no_ack` results are not treated as proof that the operation did not execute; the UI preserves `invoke_id`, `client_id`, `command_id` and `reason`.

Only SUBMITTED receipts are eligible for provider polling. REJECTED, ABORTED and UNKNOWN remain terminal local outcomes and do not trigger chain RPC polling. The source tests and CI cover these rules; no claim of live Cloud Agent validation is made.

## Remaining release gates

| Gate | Status | Evidence / next action |
|---|---|---|
| Merged source and main CI | **PASS** | [Run 42874904974](https://github.com/rudimentall1/verigate/actions/runs/42874904974): 613 Python tests, 64/64 UI, Contracts, schema-4 validation and Linux 0.1.17 binary smoke test. |
| Linux Executa 0.1.17 archive | **PASS in CI** | Extracted package smoke test completed successfully in the same run. |
| Windows/macOS Executa 0.1.17 archives | **BLOCKED / not evidenced** | Run the four-target workflow with version 0.1.17 and `publish_release=false`; inspect each extracted package and smoke-test result. |
| Fresh Anna Cloud Agent installation and invoke | **BLOCKED / not evidenced** | Install the candidate in a fresh Cloud Agent and verify tool registration, `describe`, safe invoke, App-scope APS KV/ETag operations, and failure/late-result behavior. |
| Anna Console immutable cut | **NOT DONE** | Recheck the current Console state, then cut App 0.1.30 with the intended Executa 0.1.17 bundle only after the preceding evidence is accepted. |
| Anna review / Marketplace publication | **NOT DONE** | No review submission or publication is evidenced. |
| Successful signed wallet submission / on-chain settlement | **NOT PROVEN** | The 9 November live recording ends with the user rejecting MetaMask's signature. No transaction hash, broadcast or settlement is proven by that recording or CI. |

## Product and security boundaries

- Native USDC wallet hand-off is implemented for Base and Ethereum. Solana policy checks and signed authorizations exist, but Solana wallet submission is not included in this App.
- The 9 November recording ends with the user denying the MetaMask signature after ExecutionRouter consumed the one-time authorization. This intentionally burns that permission; a fresh policy check and new permission are required. The rolling 24-hour budget counts non-BLOCK authorization records, not chain-confirmed transfers.
- Accounting is scoped to one persistent Executa installation. Separate Cloud Agent workspaces or issuer keys are not aggregated into one account-wide budget.
- The App gates the supported Verigate App/ExecutionRouter path. It is not a universal firewall for external wallets or actions that bypass that router.
- No independent third-party security audit, hosted multi-tenant service, production KMS/HSM custody or key-rotation service is shipped.

**Release rule:** do not describe this App as approved, published, or payment-successful until those states are independently verified in Anna and, for payment success, on-chain.

## Verification entry points

- [Anna App implementation and Runtime acceptance notes](../README.md)
- [Anna documentation index](README.md)
- [Anna platform compatibility review — 10 November 2026](ANNA-PLATFORM-COMPATIBILITY-2026-11-10.md)
- [Live MetaMask integration checkpoint — 9 November evidence](history/SESSION-CHECKPOINT-2026-11-10-LIVE-METAMASK.md)
- [Historical release-gate record](history/RELEASE-GATE-2026-11-09.md)
- [Repository threat model](../../docs/threat-model.md)
- [Anna release CI](https://github.com/rudimentall1/verigate/actions)
