# Anna App — current release status

**Updated:** 2026-11-11  
**Anna App / Executa source:** commit `6eca3bd782fe54ca798ac3fd66a54acde61b41fc`  
**Source candidate:** Anna App **0.1.30** · bundled Executa **0.1.17**  
**Current Anna Console state (11 November):** immutable Draft App **0.1.30** · version ID **2109** · App ID **851**; bundled Executa **0.1.17** · version ID **1063** · Executa ID **1314**

## Current source candidate — 11 November

PR [#44](https://github.com/rudimentall1/verigate/pull/44) is merged into `main`. Its source candidate is App 0.1.30 / Executa 0.1.17. The source manifest requires bundled Executa >= 0.1.17.

The source candidate was pushed and cut in Anna Console as immutable Draft App 0.1.30 / bundled Executa 0.1.17. It remains **Draft** and has not been submitted for review or released to the Marketplace. A live invocation through Cloud Agent #7883 is now verified; a second clean Agent installation and live APS KV/ETag concurrency behavior remain unverified.

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

**Historical boundary (Developer API check, before the later Dashboard verification):** the authenticated developer CLI could read/write Developer Console state, but its credential received HTTP 401 from the user-runtime endpoints `GET /api/v1/apps/installed` and `GET /api/v1/agents`; it did not expose the user-facing App-install flow. That API check alone established no Cloud Agent installation or invocation. The later signed-in Anna Dashboard inspection and live invocation are recorded in **Cloud Agent runtime confirmation — 11 November 2026** below; that later evidence supersedes the earlier "not yet verified" status for one existing Agent. A second clean Agent installation remains unverified.


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

### First-payee threshold versus dynamic authority — interpretation

The **50 USDC first-payee threshold** and the **PROBATION 50 USDC per-action authority ceiling** are separate controls:

- The DOCX case for **50.01 USDC** was replayed with isolated state and a previously unseen recipient. It returns **WARN** because the first-authorization threshold is exceeded.
- Recipient history is installation-scoped and persists after a non-BLOCK authorization. A later request to the same recipient is no longer a first-payee request; do not expect the first-payee rule alone to keep returning WARN.
- The independent PROBATION ceiling still prevents issuing an Execution Authorization above **50 USDC/action**, even if the policy preview returns ALLOW after recipient history exists.
- Therefore, a policy ALLOW above 50 USDC is not an execution bypass. The authorization button must remain unavailable until the dynamic authority state permits the amount.

Do not describe the difference between a fresh isolated fixture and a previously used Anna installation as a policy regression. To compare the same case, reset to a genuinely fresh issuer installation or use a new recipient and explicitly record the installation history. No new 50.01 live-session result is claimed here.

### Live Anna Dashboard acceptance — 11 November

The signed-in Brave session was switched to the actual **Dashboard - Anna** tab, and the loaded App document identified **Verigate Authority 0.1.30**, App ID **851**, immutable version ID **2109**. These observations are from the Anna App document, not from the surrounding ChatGPT conversation.

Observed App behavior in that session:

- **12.50 USDC / Ethereum / valid EVM recipient:** Anna AI returned a contextual interpretation; Verigate displayed **ALLOW**, the Ed25519 Decision Receipt verified, and the UI reported that the current PROBATION authority covered the amount. No authorization or payment was issued for this preview.
- **10 USDC / Solana / `YOUR_SOLANA_WALLET_ADDRESS`:** the App first requested confirmation of extracted details. After confirmation, Verigate returned **BLOCK** with `invalid_payee` because the placeholder is not a valid Solana address. No payment was sent. Solana wallet submission is not supported by this App version.
- **0.000001 USDC / Base:** the prior live wallet hand-off produced SUBMITTED receipt `0xcd36b8c135074b6083fd650c8a0f686d4ffa125657d1e18964ac8ac6180c489c`. The independent Base RPC check reported receipt status `0x1`, block `0x355cb64`, and a USDC Transfer event for exactly one base unit (0.000001 USDC). This is one verified micropayment, not proof that the full 18-case matrix has passed live.

The 18-case DOCX matrix remains **local UI + real Executa subprocess QA with scripted Anna Sampling fixtures**, not 18 live Anna LLM runs. The live Anna Dashboard checks above are a separate, smaller evidence set. Do not merge the two evidence classes.

The 18-case local matrix does not prove live Anna LLM comprehension. Separately, the live Cloud Agent invocation is confirmed below. The remaining platform-level gaps are live APS storage/ETag behavior (including concurrent conditional-delete semantics), a second clean Agent installation, and a new end-to-end wallet session. The E2E wallet provider is simulated; the recorded real MetaMask hand-off remains the 9 November attempt, which ended with the user rejecting the signature after ExecutionRouter consumed the permission. The 11 November micropayment is separately recorded above.

### Cloud Agent runtime confirmation — 11 November 2026

The signed-in Anna **Agents** page and Cloud Agent plugin details were inspected after the live Dashboard checks:

- Cloud Agent **#7883** is **Running / Online**, provider **Fly**, region `sin`, machine ID `d8950d4be16208`, registered two days earlier. The Dashboard's selected/default Agent indicator carries the matching machine ID suffix `d8950d4be16208-5ebce57b`.
- The Cloud Agent plugin inventory shows the App-bound Executa tool ID `tool-verigate-authority-verigate-authority-28x5jku8`, version **0.1.17**, status **Running**, with **9 tools**.
- The immutable App **0.1.30** / version ID **2109** was open in the Anna Dashboard. Its live request returned an Anna AI contextual-review response from the bundled Executa, followed by Verigate's deterministic **BLOCK / invalid_payee** for the deliberately invalid Solana placeholder. No payment was sent.
- This confirms a live invocation path through the current Cloud Agent and the current App-bound Executa 0.1.17. It is not merely the local scripted E2E fixture.

The account currently reports Cloud Agents **1/1**. A separate clean Cloud Agent could not be provisioned without freeing capacity; no existing Agent was suspended, destroyed or modified. Therefore the **live Cloud Agent invoke** sub-gate is now **PASS**, while a **fresh, separately provisioned Cloud Agent installation** remains untested. The Cloud Agent inventory also contains a separate legacy Verigate tool ID `tool-rinat-verigate-authority-2um8gwhw` at version **0.1.15**, still Running; it was left untouched. App 0.1.30 is bound to the distinct 0.1.17 tool ID above.

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

## Subsequent SDK and authorization-race tests — 11 November

Two test-only changes were merged after the App 0.1.30 / Executa 0.1.17 immutable Console cut. They do not change the published or immutable Anna Console artifact:

- [PR #48](https://github.com/rudimentall1/verigate/pull/48), merged as `a9b9185b21a39dff6f94f87dfc116fd8e5ac99c1`): SDK transport tests prove a timed-out APS request discards a late host response and a conditional-delete `precondition_failed` response remains a `StorageError`. [CI run 42982549110](https://github.com/rudimentall1/verigate/actions/runs/42982549110) passed.
- [PR #49](https://github.com/rudimentall1/verigate/pull/49), merged as `8f37da587508c0b4f5b2d60298be9cb98b6338d7`): a deterministic two-consumer race test proves exactly one consumer wins against the fake APS adapter's atomic conditional-delete behavior. [CI run 42983061855](https://github.com/rudimentall1/verigate/actions/runs/42983061855) passed all three jobs: Python full suite, contracts and Anna UI E2E.
- [PR #50](https://github.com/rudimentall1/verigate/pull/50), merged as `4f51860a6c1cca8b8e75ece767c8b87343f87ceb`): fixes a pending reverse-RPC entry leak when a caller cancels an in-flight StorageClient/FilesClient request. `asyncio.CancelledError` now removes the pending request under lock and is re-raised; the regression test verifies that a late host response is ignored and `_pending` is empty. [CI run 42983839829](https://github.com/rudimentall1/verigate/actions/runs/42983839829) passed all three jobs: Python full suite, contracts and Anna UI E2E.
- Current `main` includes PR #50 at `4f51860a6c1cca8b8e75ece767c8b87343f87ceb`.

**Evidence boundary:** these are SDK-local and fake-adapter tests. They do not establish that live Anna APS implements atomic ETag-conditional deletion under concurrent Cloud Agent requests. That remains a release gate and must not be represented as platform-verified.

## Remaining release gates

| Gate | Status | Evidence / next action |
|---|---|---|
| Merged source and main CI | **PASS** | Original App 0.1.30 / Executa 0.1.17 source validation: [run 42874904974](https://github.com/rudimentall1/verigate/actions/runs/42874904974). Subsequent SDK, fake-adapter race and caller-cancellation regression tests are merged on current `main`; [PR #50 CI run 42983839829](https://github.com/rudimentall1/verigate/actions/runs/42983839829) passed Python full suite, contracts and Anna UI E2E. |
| Linux Executa 0.1.17 archive | **PASS in CI** | Extracted package smoke test completed successfully in the same run. |
| Four-platform Executa 0.1.17 archives | **PASS** | [Run 42959224224](https://github.com/rudimentall1/verigate/actions/runs/42959224224): all four reproducible builds, extracted-package smoke tests, artifact uploads and independent SHA-256/manifest checks passed. Workflow artifacts expire 9 February 2027. |
| Fresh Anna Cloud Agent installation and invoke | **PARTIAL PASS** | Cloud Agent #7883 is Online; App 0.1.30 invoked its App-bound Executa 0.1.17 and received a live Anna AI Sampling response. A second clean Agent installation remains untested because Cloud Agent capacity is already 1/1. Live APS KV/ETag semantics and platform-level failure/late-result behavior remain unverified; SDK-local timeout and stale-response handling are covered by PR #48. See Cloud Agent runtime confirmation below. |
| Anna Console immutable cut | **PASS** | App 0.1.30 / version ID 2109; Executa 0.1.17 / version ID 1063; four platform archives uploaded to Anna CDN; App remains Draft. |
| Anna review / Marketplace publication | **NOT DONE** | No review submission or publication is evidenced. |
| Successful signed wallet submission / on-chain settlement | **PARTIAL PASS** | One 0.000001 USDC Base transfer was submitted through the live Anna App and independently checked by Base RPC (receipt status 0x1; see the 11 November live Dashboard acceptance section). This does not validate every positive request or every supported network. |

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
