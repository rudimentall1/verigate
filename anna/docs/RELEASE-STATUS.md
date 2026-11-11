# Anna App — current release status

**Updated:** 2026-11-11  
**Repository source candidate:** commit `6eca3bd782fe54ca798ac3fd66a54acde61b41fc` on `main`  
**Source candidate:** Anna App **0.1.30** · bundled Executa **0.1.17**  
**Current Anna Console state (11 November):** immutable Draft App **0.1.30** · version ID **2109** · App ID **851**; bundled Executa **0.1.17** · version ID **1063** · Executa ID **1314**

## Current source candidate — 11 November

PR [#44](https://github.com/rudimentall1/verigate/pull/44) is merged into `main`. Its source candidate is App 0.1.30 / Executa 0.1.17. The source manifest requires bundled Executa >= 0.1.17.

The source candidate has now been pushed and cut in Anna Console as immutable Draft App 0.1.30 / bundled Executa 0.1.17. It is still **Draft**: it has not been submitted for review or released to the Marketplace. Cloud Agent installation and invocation have not yet been verified.

### Exact-source main CI

[GitHub Actions run 42874904974](https://github.com/rudimentall1/verigate/actions/runs/42874904974) ran on the merged `main` commit and completed successfully. All three jobs passed:

- Python unittest suite: **613 tests passed**; demo and API app smoke checks passed.
- Anna UI: strict schema-4 validation passed; **64/64 UI flow tests passed**.
- Contracts: atomic-state end-to-end and access-control tests passed.
- Linux Executa 0.1.17 was built, packaged, extracted and smoke-tested. The log records a successful `describe`, ALLOW decision, signed receipt, one-time App-scope approval consumption, one-time wallet-handoff consumption, and persisted/verified SUBMITTED receipt.

This proves the merged source and the Linux CI path. It does not prove a fresh Anna Cloud Agent installation, a live invocation in Anna, or a successful on-chain payment.

### Executa 0.1.17 platform packages

The four-target workflow completed successfully in [run 42959224224](https://github.com/rudimentall1/verigate/actions/runs/42959224224), against source commit `6eca3bd782fe54ca798ac3fd66a54acde61b41fc`, with input `version=0.1.17` and `publish_release=false`.

For **each** target, the workflow:
- built the executable twice and reported `REPRODUCIBILITY PASS`;
- packaged version 0.1.17 and extracted the resulting release archive;
- ran the extracted entrypoint through `describe`, ALLOW decision, signed receipt, one-time App-scope approval, one-time wallet hand-off and persisted/verified SUBMITTED receipt;
- verified the package SHA-256 against its generated `.sha256` sidecar, then uploaded the package and checksum sidecar as a workflow artifact.

The four downloaded workflow artifacts were independently inspected here: each contains exactly one platform release archive and its checksum sidecar; each archive contains a root `manifest.json` declaring version **0.1.17** and the expected platform entrypoint. The SHA-256 recomputed over every downloaded archive matched both its sidecar and the workflow smoke-test log.

| Target | Artifact ID | Entry point | Release archive SHA-256 |
|---|---:|---|---|
| Linux x86_64 | `13827958251` | `verigate-authority` | `358c3f37c9750010a6f37bcddb9506b55cee0cec933e5be9d2d1b5cc09517010` |
| Windows x86_64 | `13828342753` | `verigate-authority.exe` | `b19024bbfd1546539a4e149856908159ba7b85fb91b055b4b302d70e8587f05e` |
| macOS ARM64 | `13828337795` | `verigate-authority` | `89cb4f2c0c0c67b63b0f37a2b3fe24252a2166b11c499435f3ecf6ce7a7988f4` |
| macOS Intel x86_64 | `13827999561` | `verigate-authority` | `1a1e6e0b5865e4aa594a3eea62bb97d66462a4471fe4e6913e4d890ab49ba81e` |

These are **workflow artifacts, not a published GitHub Release**. GitHub reports their expiration as **9 February 2027**. The release job was skipped as intended. The newest GitHub Release listing still shows draft Executa **0.1.14**; no 0.1.17 release was published. Do not confuse the downloadable workflow artifacts with a permanent release or with an Anna Console bundle.

## Anna Console state

The last recorded Console inspection on 10 November confirmed:

- App ID **851**, immutable Draft version **0.1.29**, version ID **2097**.
- Bundled Executa ID **1314**, version **0.1.16**, version ID **1042**.
- The App was in **Draft** state, not Marketplace-published and not submitted for review.

This snapshot predates PR #44. Recheck the Console before changing or cutting any immutable version. Do not overwrite or remove the existing Draft as part of source-level work.


### Anna Console cut — 11 November

The exact source checkout at commit `6365bb9983baa90fb2912a93fc7bcd938a4d8220` was validated with Anna CLI 0.1.64 strict schema-4 validation, then pushed and cut through the official CLI against `https://anna.partners`.

- App ID **851**, slug `verigate-authority`, working revision **11**, final bundle status **ready** (3 files, 95.9 KB; 2/3 files deduplicated on upload).
- Immutable App version **0.1.30**, version ID **2109**.
- Executa ID **1314**, tool ID `tool-verigate-authority-verigate-authority-28x5jku8`, visibility **app_bundled**, immutable version **0.1.17**, version ID **1063**.
- The cut uploaded **all four** version 0.1.17 platform archives to Anna CDN (4 uploaded, 0 cached). Executa version content hash: `0bcdb7d2897f282eb6c2f3f723b9ba22be052a0b32c956afcd905bd0beea91a9`.
- Post-cut `apps status` confirmed App status **draft**, `is_published=false`, `published_at=null`, latest immutable App record 0.1.30 / ID 2109, and version count 10. Executa status confirmed `is_published=false` and Executa latest version 0.1.17 / ID 1063.
- No `apps release`, review submission or Marketplace publication was run. App 0.1.29 / ID 2097 remains in version history and was not overwritten.

The Cloud Agent test is a separate gate. The authenticated developer CLI can read/write Developer Console state, but the available developer credential receives HTTP 401 from the user-runtime endpoints `GET /api/v1/apps/installed` and `GET /api/v1/agents`. The CLI does not expose the user-facing App-install flow. No Cloud Agent install or invocation is claimed from these Developer API calls. Use the signed-in Anna web UI / authorized user session to install the immutable Draft on a test Agent, then verify deployment status and run safe `describe` / `invoke` checks.


### Windows QA — DOCX request matrix and full local suites, 11 November

All local validation below used a separate clean temporary checkout of source commit `6365bb9983baa90fb2912a93fc7bcd938a4d8220`; neither of the user's existing working directories was changed.

- Anna CLI **0.1.64** strict schema-4 validation: PASS.
- Anna UI E2E: **64/64 passed** in 207.5 seconds. The real `bundle/app.js` and real Python Executa subprocess were exercised; only Anna host Sampling was scripted. This does not consume Anna CU and is not a live Cloud Agent run.
- Python unittest suite on Windows / Python 3.10: **613 passed**, **4 skipped** because POSIX file-mode checks are not portable to Windows. The only emitted warning was a Starlette/httpx test-client deprecation warning.
- All **18 exact request texts** from the user's `Запросы.docx` were replayed through the App UI + real Executa subprocess with isolated state for each case. The model interpretation was a scripted fixture matching the intended fields; the matrix validates policy/UI behavior, not actual natural-language comprehension by Anna's live LLM.

| DOCX case | Observed result | Additional behavior |
|---|---|---|
| 0.000001, 1.37, 25, 49.99, 50 USDC on Base | **ALLOW** | All remain at or below the 50 USDC first-payee cap. |
| 50.01 USDC on Base | **WARN** | First-payee cap exceeded; execution button disabled by PROBATION authority ceiling. |
| 250.01, 300, 500 USDC on Base | **WARN** | Human-review threshold applies; execution remains disabled because current PROBATION authority is capped at 50 USDC/action. |
| 600 USDC on Base | **BLOCK** | Per-transaction cap 500 USDC exceeded. |
| 0 USDC on Base | **CLARIFY** | UI asks for a positive amount; no policy check is run. |
| 25 USDC to `0xabc` | **BLOCK** | Invalid EVM recipient format. |
| 25 DAI on Base | **BLOCK** | Only USDC is allowed by this App policy. |
| 25 USDC with prompt-injection/override text | **WARN** | Explicit `prompt_injection` risk flag shown; policy cannot be relaxed by the model. |
| Russian request for 13.75 USDC on Base | **ALLOW** | The scripted interpretation passed the exact fields to policy. |
| 17.428913 USDC on Base | **ALLOW** | Exact six-decimal EVM amount preserved. |
| 12.50 USDC on Ethereum | **ALLOW** | Supported EVM network. |
| 10 USDC on Solana with `YOUR_SOLANA_WALLET_ADDRESS` | **BLOCK** | Placeholder is not a valid Solana Base58 address; no valid Solana address was supplied in the document. |

**Important distinction:** policy WARN does not imply that Execution Authorization can be created. On a fresh installation, dynamic authority is **PROBATION / 50 USDC per action**. The App disables permission creation above that independent ceiling even where policy returns WARN for human review. Increasing that ceiling requires the documented verified authority progression; changing the AI response or approving the WARN cannot override it.

These results do not close the Cloud Agent gate. They do not prove live Anna Sampling, actual Cloud Agent deployment, real APS storage/ETag behavior, live `describe`/ `invoke`, or a real injected EIP-1193 wallet session. The E2E wallet provider is simulated. The only recorded real MetaMask hand-off remains the 9 November attempt, which ended with the user rejecting the signature after ExecutionRouter consumed the permission.

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
| Four-platform Executa 0.1.17 archives | **PASS** | [Run 42959224224](https://github.com/rudimentall1/verigate/actions/runs/42959224224): all four reproducible builds, extracted-package smoke tests, artifact uploads and independent SHA-256/manifest checks passed. Workflow artifacts expire 9 February 2027. |
| Fresh Anna Cloud Agent installation and invoke | **BLOCKED / not evidenced** | Developer CLI authentication cannot access user-runtime endpoints or the Installed Apps UI. Install immutable App 0.1.30 on a test Agent through the signed-in Anna web UI; verify deployment, real `describe`, safe invoke, APS KV/ETag, and failure/late-result behavior. |
| Anna Console immutable cut | **PASS** | App 0.1.30 / version ID 2109; Executa 0.1.17 / version ID 1063; four platform archives uploaded to Anna CDN; App remains Draft. |
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
