# Verigate Authority — latest checkpoint 2026-11-08

> The older notes below are historical. The authoritative App/review/Executa state is in the latest update appended at the end of this file.

**Updated:** 2026-11-08
**Repository:** https://github.com/rudimentall1/verigate
**Active worktree:** `C:\Users\User\verigate-anna-release` (original checkout `C:\Users\User\verigate` untouched)
**Branch / base commit:** `fix/anna-sampling-capability` at `408a3010b31e138f627dd679ab586d7d0f79d394`. Build reproducibility edits and checkpoint updates described at the end are local-only and uncommitted.
**Current source metadata:** Anna App `anna/app.json` synchronized locally to `0.1.21`; bundled Executa remains at `0.1.15`.
**Untracked local tooling:** `_tools/` and `_anna-screen.png`; do not stage them.

## Prior Anna platform snapshot — superseded by the authoritative update at the end

- App `verigate-authority`, ID `382`: immutable App `0.1.20`, version ID `2047`, now the latest version. Overall app status remains `PENDING_REVIEW` because `0.1.19` / ID `2044` is still pinned in review. App `0.1.20` is NOT submitted for review and NOT Marketplace-released.
- Bundled Executa `tool-rinat-verigate-authority-2um8gwhw`: version `0.1.15`, version ID `1029`. App `0.1.20` froze this exact Executa version. Four binary artifacts were verified as identical to the previously published content; platform response: `0 uploaded, 4 cached`.
- App CLI operation succeeded using `apps publish` (stage + immutable cut), `--skip-executa-publish`, and explicit production `--executa-id`. No `apps release` or `apps submit-review` was executed.
- New App cut output: `apps/verigate-authority: cut immutable version 0.1.20 (version_id=2047)`; frozen dependency: `tool-rinat-verigate-authority-2um8gwhw -> executa_version=1029 (v0.1.15)`.
- Current review pointer is unchanged: `in review: v0.1.19 (pinned at submit-review)`. Do not claim 0.1.20 is in review or live.
- App manifest requires bundled Executa minimum version `0.1.15`. Executa manifest and Python runtime declare `host_capabilities: ["llm.sample"]`; this declaration does not itself grant the runtime permission. A real Cloud Sampling grant/response remains unverified.

## Recovered upload procedure and binary integrity

- Previous PowerShell history confirms the established method: `anna-app apps publish` from the Anna project directory, with `--skip-executa-publish` and `--executa-id verigate-authority=tool-rinat-verigate-authority-2um8gwhw`. It is a composite command: `apps push` (working draft + UI bundle) followed by `apps cut` (immutable snapshot).
- The failed first attempt was caused by a locally rebuilt Windows package changing the `binary_sha256` for already-published Executa `0.1.15`. Anna correctly rejected mutating an immutable version.
- Restored all four exact `0.1.15` release archives from successful four-platform workflow `42485119112` (published artifacts; release publication disabled). Their SHA-256 values were checked against the workflow's `.sha256` sidecars and then restored in `anna/executas/verigate-authority/dist/`:
  - `linux-x86_64`: `b029606e0b73d5677b277bb6ee5ca3fa6ab1f5cd42155a12559eca10e272ef8e`
  - `windows-x86_64`: `57ee73192da1a75f3abae2a92ddad5bb0073a2722d19bfe5e71607d2ca22cfd6`
  - `darwin-arm64`: `08a4d3229c9ce467114abebf8f9609c459a1c6789056ee0a7e6a4c36a3bf0904`
  - `darwin-x86_64`: `c9811701b250f7b95eca5c43af3325c4295564918bfc4ec881f65adfa42f8231`
- Verified restored Windows `0.1.15` archive with `anna/smoke_package.py windows-x86_64 0.1.15`: PASS (describe, signed ALLOW, App-scope approval consumed once, wallet hand-off consumed once, submitted receipt persisted/verified). Anna subsequently recognized all four platform artifacts as already published/cached.

## Latest verified local and CI results

- Python full suite: `621 passed, 4 skipped`, 3 upstream deprecation warnings (exit 0).
- Anna UI E2E: **47/47 passed** on the uploaded source, covering free-form Russian/English, `123.456789 USDC`, missing Executa, host 401, Sampling grant denial, signed Intent and explicit authorization.
- `tests/test_anna_sampling_roundtrip.py`: **1 passed** (mock host only; protocol/framing, not Cloud acceptance).
- `npm run test:atomic`: passed; stale authorization produced zero side effects, fresh authorization one.
- `npm run test:guard`: passed; executor/attacker/stale-state/value mismatch rejected and exact value forwarded.
- Anna CLI 0.1.64 `validate --strict`: passed (schema 4, dispatcher 0.33.0).
- `git diff --check`: passed before this checkpoint refresh. Windows original packaged binary smoke passed as detailed above.
- GitHub Actions run `42492077034` for commit `1cc9b64e584b59c15150c550de2eb13b24db8a50`: all jobs `test`, `contracts`, and `anna-ui` SUCCESS.

## Latest code changes included in App 0.1.20

- `askAnna()` no longer converts arbitrary `tools.invoke` failures into an apparent LLM outage. Missing Executa and host invocation/permission/transport errors surface explicitly and do not run a policy-only preview.
- Only an explicit Executa Sampling-unavailable response can enter the clearly labelled policy-only fallback; that fallback uses only explicit form fields and cannot create execution authority.
- Sampling error code and host reason are preserved in the visible review summary.
- Regression coverage verifies free-form Russian/English requests and non-round decimal amounts reach Sampling unchanged without lexical or fixed-amount allowlists.
- No signed-receipt, dynamic-authority, explicit confirmation, one-time approval, ExecutionRouter or wallet-submission security checks were removed or weakened.

## Still unverified / do not overclaim

- Real Anna Cloud Agent install, actual platform-issued Sampling grant, real `sampling/createMessage` LLM response, APS persistence/restart, and runtime permission state remain unverified. Local mocks and CI are not Cloud acceptance. Earlier checkpoint records Anna CU quota exhaustion.
- App `0.1.20` is uploaded and immutable, but deliberately not submitted for review and not released. `0.1.19` remains the pinned review version.
- The generated `anna/bundle/anna-tool-ids.js` is gitignored and generated by CLI during publish; do not stage it.

---

## 1. User requirements that must not be lost

- Payment amounts are **not restricted to 50 or 250 USDC**. The UI/input/parser and EVM amount builder must accept arbitrary positive USDC values, including non-round values, with up to 6 decimal places. Whether a particular amount can receive execution authority is a separate policy/dynamic-authority decision.
- **50 USDC and 250 USDC are policy thresholds, not a list of allowed payment values.** Current policy semantics: `new_payee_cap = 50 USDC`, `confirmation_required_over = 250 USDC`, `per_tx_cap = 500 USDC`, `daily_cap = 2,000 USDC`, `rate_limit_per_minute = 30`. The first two influence risk/decision behavior; they do not mean only 50 or 250 may be entered.
- “Arbitrary amounts” does not silently mean unlimited transfers. Current configured per-transaction and daily limits still apply unless the user explicitly changes product policy. Do not hardcode 50/250 as a dropdown, enum, accepted amount set, or fixed test-only values.
- Preserve the distinction between amount parsing/transaction construction and policy authorization. Test arbitrary values on both sides of thresholds and exact boundary behavior.
- Do not upload Anna App 0.1.18 or consume the last Anna upload attempt until the blocking issues below are resolved and the final release artifact is proven ready.
- Do not claim Anna Cloud / Cloud Agent / real APS acceptance: Anna CU quota is exhausted and no live cloud acceptance has been performed.
- Russian conversation; English code, tests, docs, and reports. Minimal safe changes; no blind refactor or mass rename. No unrelated workloads or files.

## 2. Current release/build evidence

- Latest local identity hardening: caller agent_id is a signed display label; accounting and capability state use the persistent issuer-key fingerprint principal (anna-installation:<sha256>). This is installation-scoped and does not aggregate separate Agent workspaces. Identity/backend regression file: 20/20 passed; policy and Anna authorization race/identity subset: 32/32 passed; latest App UI E2E: 43/43 passed with the real local bundle + Python Executa subprocess and fixture-backed host.

- Anna App candidate: **0.1.18**. Anna App currently has 0.1.17 / version ID 1981 in PENDING_REVIEW (App ID 382). Version 0.1.18 has NOT been uploaded/cut/submitted.
- Executa candidate: **0.1.14**.
- `npm ci` on Node 22.23.4 / npm 10.9.9 passed after fixing the nested Ganache `fsevents@2.3.2` lockfile entry to mark it optional. The lockfile fix is commit `70c52f0`.
- Exact-commit GitHub CI on `70c52f05...`: jobs `test`, `contracts`, and `anna-ui` all passed. The Anna UI job includes UI E2E and Linux Executa binary build/smoke. Run: https://github.com/rudimentall1/verigate/actions/runs/42377014780
- Another CI run passed: https://github.com/rudimentall1/verigate/actions/runs/42377009968
- Four platform Executa 0.1.14 build jobs passed (linux-x86_64, windows-x86_64, darwin-arm64, darwin-x86_64): https://github.com/rudimentall1/verigate/actions/runs/42377183564 . The workflow's GitHub Release step was SKIPPED because `publish_release=false`.
- Downloaded artifacts were checked locally. Archive SHA-256:
  - linux-x86_64: `b3f23305d82f8feaeef8197eea4d4f4b4e293ce86cfc44999e2fbd61d0fdb4dd`
  - windows-x86_64: `0453d49ca71658d112aac50f190faf208f5f157946b9fd0fc2a117ad80afb8f9`
  - darwin-arm64: `d01cb5592e7c9362f83e027317c9b1f42ed82bdca09ac515b5d9764f832340dc`
  - darwin-x86_64: `e51878cdc9dbcdec02a305906a5dd5d92fa8db1aa49dadd7c713c08702d74881`
- The four archives and checksum files are copied into `anna/executas/verigate-authority/dist`. This directory is gitignored; verify current contents before relying on it.
- Windows packaged Executa 0.1.14 smoke passed: `describe`, deterministic ALLOW, signed result, one-time App-scope approval and one-time wallet hand-off. Reported: `decision=ALLOW, signed=yes, app_scope_approval=consumed_once, wallet_handoff=consumed_once`.
- Latest Python full-suite verification after identity, EVM finality and atomic WARN-review changes: python -m pytest -q = 578 passed, 4 skipped, 3 upstream deprecation warnings, 112.73s (exit 0). Focused engine + Anna authorization regression set = 32 passed; EVM chain/RPC/outcome/lifecycle set = 24 passed.
- Latest Anna UI E2E = 43/43 passed (183.24s). Includes normal ALLOW flow, normalized display-label binding, installation-principal mismatch fail-closed, WARN review UI, dynamic-ceiling refusal, invalid-recipient BLOCK, prompt-injection WARN, one-time approvals and wallet hand-off.
- Executa runtime manifest and checked-in `anna/executas/verigate-authority/manifest.json` were synchronized. `tests/test_anna_executa_manifest.py` = **13 passed**.
- Schema-4 App validation: `cd anna && npx --yes @anna-ai/cli@0.1.64 validate --strict` = **passed**, dispatcher_version 0.33.0. Do not use the globally installed stale `anna-app` CLI (dispatcher 0.23.0 / schema max 3); it produced a false failure and is not the release validator.
- The EVM chain verifier was hardened locally: it binds the observed transaction/receipt to the signed EVM envelope (chain ID, hash, destination, calldata, value), requires the observed transaction chainId to be present and match the signed envelope, checks the receipt sender against verifier-pinned wallet enrollment, checks transaction/receipt block binding and canonical block hash, and requires a configured minimum confirmation depth before reporting SUCCEEDED/FAILED. ERC-20 transfer(address,uint256) requires the matching Transfer event. This is not yet integrated into Anna's UI/outcome path.
- Earlier Anna UI E2E runs were 38/38, 39/39 and 41/41 during incremental hardening. Current result is 43/43 and supersedes all earlier counts. UI harness executes the real App bundle + Python Executa subprocess with fixture-backed host LLM/APS calls; it is not Anna Cloud acceptance.
- Current EVM checks on the modified worktree: `npm run test:atomic` passed (`staleAuthorizationReverted=true`, stale side effect `0`, fresh side effect `1`); `npm run test:guard` passed (zero executor, attacker, stale state and value mismatch rejected; exact value forwarded). Ganache fell back from optional µWS native binding to the NodeJS implementation because `uws_win32_x64_137.node` is absent; the tests still exited 0.
- Current strict App validation: `cd anna && npx --yes @anna-ai/cli@0.1.64 validate --strict` passed on schema 4 / dispatcher 0.33.0. The globally installed stale CLI reports schema max 3 and must not be used.
- No GitHub Release was published. No Anna upload/cut/review submission/publication was performed.

## 3. Confirmed product/security findings — do not downgrade to assumptions

### A. Caller-controlled agent identity defeats per-agent quotas ? installation-scoped mitigation added locally

- Original reproducible PoC against an isolated SQLite DB: 100 requests, same payee, 40 USDC each, unique caller-controlled agent_id values. Result: **100 ALLOW**, aggregate **4,000 USDC**, 100 DB rows. This demonstrated a policy-accounting/identity-integrity bypass, not an unauthorized transfer: App approval and wallet hand-off approval were still required.
- Local remediation: the Anna Executa now derives anna-installation:<sha256(raw issuer public key)> from the persistent Ed25519 issuer key. verigate_check, verigate_policy_summary, capability IDs, persistent authorization, spend/rate accounting and dynamic authority use this canonical principal. Caller-supplied agent_id is now a bounded display label only; it remains inside signed intent/authorization metadata and the one-time App approval remains bound to that label.
- The App UI verifies that the signed preview label matches the visible input and that the signed principal matches the policy-summary principal. When execution authority is issued, it verifies the fresh receipt and authorization use the same installation principal and exact display label. The form explicitly identifies the field as display-only.
- Regression proof: tests/test_anna_execution_authorization.py rotates 50 distinct labels while authorizing 40 USDC each, reaches exactly 2,000 USDC, then confirms the 51st request under a new label is BLOCKed. The policy summary reports the same principal and accumulated 2,000 USDC regardless of the label. Targeted test file passes **20/20**.
- Scope limitation: this prevents label rotation inside one installation only. It does **not** impose a cross-Agent or account-wide quota across separate Anna Agent workspaces/issuer keys. All logical agent labels in a single installation currently share one budget and one dynamic-authority principal; real per-agent isolation needs a cryptographic enrollment/signature mechanism.
- Anna APS scope=app is per current user and current App; ETag conditional updates/deletes exist, but the KV API does not expose atomic create-if-absent. A race-safe shared principal bootstrap across independent Agent workspaces is therefore not claimed. APS semantics and Cloud lifecycle must be verified in a real Anna Cloud Agent, which cannot currently be run because CU quota is exhausted.
- Vendored InvokeContext has invoke_id, plugin_name, deadline_ms, credentials, and raw context; it has no typed user_id or authenticated principal. context.credentials contains declared credential values and is not a verified user identity. Do not revert to trusting any caller-controlled field as principal.
- The original 100-alias PoC is still evidence of the old code's defect; the new 50-alias/51st-BLOCK regression is local evidence of this mitigation. Neither proves account-wide limits or Cloud persistence.

### B. WARN review path implemented locally (regression-tested)

- The Anna UI now exposes **Review warnings & approve** for WARN, not for BLOCK. It displays the exact payment and the current warning messages/rule IDs in a separate confirmation dialog.
- After explicit approval, UI writes a distinct 60-second App-scope `payment_warning_review` record bound to the exact agent, payee, asset, network, amount, resource and reviewed warning rule IDs. The plugin consumes this record once using the same ETag-conditional APS deletion boundary as normal approvals.
- Backend re-evaluates policy fresh with `persist=False`, requires the result to remain WARN, and compares the exact sorted set of current WARN rule IDs with the reviewed list. Missing, extra, stale or changed rules fail closed. It then records a signed ALLOW decision retaining the warning rule evidence and `anna_warning_review` metadata, and uses the normal capability/dynamic-authority authorization path.
- BLOCK cannot be overridden. Dynamic authority ceilings and per-transaction capability caps remain independently enforced. Regression tests prove that warning approval does not bypass PROBATION's 50 USDC ceiling or a BLOCK result.
- `daily_cap` was changed from WARN to hard BLOCK: over-budget requests are not eligible for the warning-review path. `policies/anna.yaml`, `core/rules.py` and `tests/test_engine.py` now document and enforce this invariant. A human review must not reset or waive the rolling daily budget.
- Backend coverage: `tests/test_anna_execution_authorization.py` tests approved WARN, no-review refusal, BLOCK refusal, mismatched warning IDs, dynamic-ceiling refusal, daily-cap refusal and one-time replay protection. UI E2E covers the explicit review path and over-ceiling refusal.
- A final concurrency review found and fixed a TOCTOU gap: WARN-review previously read spend in one SQLite transaction and wrote its approved ALLOW in a second. Fresh policy evaluation, reviewed-rule matching, and the ALLOW audit write now run in one BEGIN IMMEDIATE transaction. A regression uses two independent SQLite connections at 1,960 USDC and two concurrent 40-USDC WARN reviews; exactly one is issued, the other sees BLOCK, and final spend is exactly 2,000 USDC.
- The editable Agent label is now separated from identity: accounting and capability state use the persistent issuer-key fingerprint principal for this installation. Label rotation inside one installation no longer resets spend/rate/dynamic-authority state. This is not a per-Agent or account-wide identity across separate Anna workspaces/issuer keys, and it does not prove Cloud APS runtime.

### C. Dynamic authority cannot graduate through the current Anna UI

- Default `AuthorityPolicy`: `PROBATION` multiplier 0.10, `LIMITED` 0.25, `STANDARD` 0.50, `ELEVATED` 1.00; 5 independently confirmed successes reach STANDARD, 20 reach ELEVATED. Two adverse events can move the agent to LIMITED; a critical event suspends it.
- Effective payment ceiling is the intersection of capability max-per-action (500 USDC), policy per-transaction cap (500 USDC), and the dynamic multiplier. Therefore a fresh PROBATION agent has a 50 USDC effective ceiling; STANDARD has 250; ELEVATED can reach 500. These are dynamic authority ceilings, not allowed amount denominations.
- Regression evidence: the EVM builder converts non-round amounts including 123.456789 and values above 500 to exact six-decimal base units. However, after one 10 USDC authorization, a second 123.456789 USDC authorization for the same agent/payee fails with `action exceeds dynamic authority limit` while the agent remains in PROBATION. A 37.42 USDC payment passes end-to-end and its exact calldata amount is preserved.
- The current Anna UI does not provide a trustworthy route to graduate authority: the Executa manifest has no outcome-attestation tool; `app.js` calls `eth_sendTransaction` and reports only `SUBMITTED, not yet confirmed`; the Executa wallet hand-off calls `ExecutionRouter.consume`, not `execute_with_receipt` or `confirm_execution_receipt`. It neither creates nor confirms the execution receipt required by the outcome service.
- Current uncommitted hardening now exposes the read-only dynamic authority snapshot in `verigate_policy_summary` (using `snapshot(..., persist=False)` so a preview does not write `authority_states`), and the UI shows the state/amount ceiling and disables the execution-permission button if the dynamic snapshot is missing or the amount exceeds it. A bug where `setBusy(false)` re-enabled that button was found and fixed. Targeted regression passes, and full UI E2E is now 43/43.
- This is preview/UX correctness only. The backend `authorize_with_capability` remains authoritative and continues to reject amounts over the dynamic cap. It does NOT solve the missing independently attested post-execution promotion path, nor the caller-controlled agent-ID rotation issue.
- Core `/v1/outcomes/attest` requires an independently signed attestation from a registered external/chain verifier and an existing confirmed execution receipt. The Anna wallet flow currently supplies neither.
- Consequence: without a verified promotion path, an Anna agent may remain in PROBATION indefinitely and be unable to authorize more than 50 USDC per transaction, even though parsing and EVM construction accept arbitrary amounts. This is a release/product blocker if the intended Anna experience includes arbitrary amounts above the initial ceiling.
- Do not solve this by accepting a client-supplied `success=true`, treating a wallet's tx hash as confirmation, or silently disabling dynamic authority. Design a chain-verifiable post-transaction attestation path or explicitly choose a different payment authority policy.

### D. Scale claim is not established

- Local core-policy microbenchmark: 1,000 requests, 32 workers, 0 errors, ~845 requests/sec, `persist=False`, one local Python process and one SQLite storage instance.
- This is only a core-engine microbenchmark. It excludes Anna UI, Executa stdio/RPC, APS, LLM, Cloud Agent, network latency, multi-user isolation, and persistent audit writes. It is **not** evidence that 1,000 or several thousand users are supported.
- Core storage shares a SQLite connection protected by `threading.RLock` and `BEGIN IMMEDIATE`; privileged synchronous routes may block the asyncio event loop. This is a risk to measure, not yet a confirmed production bottleneck.
- Do not claim “thousands of concurrent users” until an end-to-end load test exists with persistent writes, multiple principals, concurrent invoke/reverse-RPC context, error/latency percentiles, and resource measurements.

### E. Anna Cloud / APS remains unverified

- Anna CU quota is exhausted. No real Anna Cloud Agent E2E, real LLM Sampling, host-attested App-scope APS isolation, `ANNA_WORKSPACE_DIR` injection, restart persistence, or image-upgrade persistence was verified.
- Local mocks and local packaging are not Cloud acceptance.
- Solana remains policy/authorization-only. Native USDC wallet hand-off supports Base and Ethereum only.
- The product is a pre-execution gate for the integrated Verigate App / ExecutionRouter path, not a global wallet firewall; independent transactions through other wallets/clients are outside this app's interception scope.

### F. EVM chain-verifier accepted unrelated successful transactions (local fix added; Anna integration remains blocked)

- Before the local hardening, `EVMChainVerifier.verify_receipt` treated receipt status `0x1` as `SUCCEEDED` without fetching the actual transaction or comparing it with the signed `authorization.payload.action.metadata.evm_transaction`.
- Reproducible mocked-RPC PoC: a signed authorization specified a Base USDC-token destination and transfer calldata; the RPC returned a successful receipt with the same requested transaction hash but a different `to` address (`0x...dEaD`) and no logs. The old verifier still returned `SUCCEEDED`. This demonstrated an authorization-to-effect binding flaw in the verifier, not an exploit of the current Anna UI (which does not call this verifier).
- Local remediation in `enforcement/evm_rpc.py` and `enforcement/chain_verification.py`: added `eth_getTransactionByHash`; require the requested hash to match the returned transaction and receipt; require RPC chain ID to match the signed envelope; compare transaction destination, input/calldata and value with the authorized envelope; compare receipt destination and sender to the transaction; and for ERC-20 `transfer(address,uint256)` require a matching Transfer event from the authorized token contract, with the exact sender, recipient and amount.
- Regression tests cover matching transaction success, pending status, unrelated destination, calldata drift, receipt-hash mismatch, ERC-20 Transfer-event presence/absence, wrong verifier-pinned sender, insufficient confirmation depth, non-canonical block hash and RPC block-number binding. The chain/RPC/outcome/lifecycle targeted suite passes 24/24 and these tests are included in the latest full Python result: 578 passed, 4 skipped, 3 warnings.
- Scope limitation: this local fix only hardens the generic verifier. It does not integrate verifier/attestation into Anna. The Anna UI still reports `SUBMITTED, not yet confirmed`, and the Executa wallet flow consumes the one-time permission without calling `execute_with_receipt` / `confirm_execution_receipt` or recording a confirmed outcome.
- Residual requirements before production use: the verifier's expected_sender and min_confirmations are constructor-pinned trust configuration, but no governed wallet-enrollment registry currently provisions them; only a separately operated verifier may instantiate this class from such a registry. Confirmation depth is a risk threshold, not absolute finality; there is no post-attestation reorg monitor/reversal workflow. The chain verifier still does not sign a CHAIN_VERIFIER outcome attestation, and no separately governed CHAIN_VERIFIER service is integrated with Anna. Do not interpret local verifier hardening as a complete outcome path or production wallet identity.

## 4. What to do next - ordered, minimal, evidence-driven

1. **Amount path is partly verified.** UI uses a free numeric amount input; EVM builder uses Decimal and exact six-decimal USDC base units. Regression tests cover arbitrary non-round values (including 37.42 and 123.456789), exact 50/250/500 boundaries, more-than-six-decimal rejection and conversion above the static cap (conversion only, not authorization). There is no fixed 50/250 denomination list. Actual execution remains gated by static policy and dynamic authority. PROBATION's current dynamic ceiling remains 50 USDC.
2. **Still unresolved / highest product blocker:** connect wallet submission to a signed SUBMITTED ExecutionReceipt, confirm it against the hardened chain verifier, and deliver an independently signed CHAIN_VERIFIER OutcomeAttestation. Anna currently sends with eth_sendTransaction in the UI and retains only the hash/display state; Executa consumes the one-time permission but does not persist the receipt. The verifier must be a separate service/key, governed independently from the issuer. No self-attestation or client-supplied success=true.
3. **Still unresolved:** provision a governed wallet-enrollment registry and network-specific finality policy for the external verifier. Its expected_sender and min_confirmations constructor values must come from this trusted registry/config, never from the submitted transaction or a free caller field. Confirmation depth reduces reorg risk but does not provide absolute finality; define monitoring and reversal for post-attestation reorgs.
4. **Partially mitigated:** caller-controlled Agent label rotation is blocked within one issuer installation by deriving the policy/accounting principal from the persistent issuer public-key fingerprint. All labels in that installation share one budget. Cross-Agent/account-wide aggregation across different Anna workspaces or issuer keys remains unresolved and requires a trusted platform principal plus a concurrency-safe shared ledger. Cloud workspace/key persistence remains unverified.
5. Local SQLite atomicity is now regression-tested across two independent connections for both plain payment evaluation and WARN-review authorization. Still required: multi-process/Executa invoke/reverse-RPC load tests with persisted audit rows and independently enrolled principals. Measure p50/p95/p99 latency, errors, throughput and event-loop stalls; separate observed results from any capacity claim.
6. Review the completed WARN-review design and exact UI copy during final diff review; ensure every review record binds the whole payment and warning-rule set.
7. Re-run exact CI and all artifact integrity checks after any code change. Rebuild all platform Executa artifacts from the final commit; the existing prebuilt archives were built from old HEAD and are not final binaries.
8. Only after all blocking release criteria are met and Anna Cloud testing is possible, reconsider one Anna upload/cut for App 0.1.18 + Executa 0.1.14. Never use the last upload attempt as a debugging experiment.
9. Review PR #24 and the stale main branch/homepage URL. Do not merge the 165-commit divergence automatically; inspect the intended mainline/base history first. The root README/homepage currently points at main, which may expose an older App version (0.1.3 / manifest schema 3) to reviewers.


## 5. Operational guardrails

- Current uncommitted worktree changes (not pushed; 22 files): anna/README.md, anna/app.json, anna/bundle/app.js, anna/bundle/index.html, anna/executas/verigate-authority/manifest.json, anna/executas/verigate-authority/verigate_authority_plugin.py, core/authority_state.py, core/engine.py, core/rules.py, docs/ANNA-RELEASE-GATE.md, docs/SESSION-CHECKPOINT.md, docs/threat-model.md, enforcement/chain_verification.py, enforcement/evm_rpc.py, policies/anna.yaml, scripts/test_anna_ui.mjs, tests/test_anna_execution_authorization.py, tests/test_chain_verification.py, tests/test_dynamic_authority.py, tests/test_engine.py, tests/test_evm_rpc.py, tests/test_money.py. git diff --check passes (CRLF normalization warnings only).
- Latest identity, finality and atomic WARN-review changes are local and uncommitted. Final local verification: Python 578 passed / 4 skipped / 3 warnings; Anna UI 43/43; EVM atomic + guard passed; schema-4 validate --strict passed. Chain/RPC/outcome/lifecycle targeted tests 24/24. No Anna Cloud acceptance was performed.
- Before further modifying files: `git status --short --branch`, current SHA, inspect the exact target code/tests.
- Do not stage or commit `.anna`, `node_modules`, `.pyinstaller`, or `dist`.
- Do not publish a GitHub Release or run Anna publish/cut/review/release commands without explicit authorization.
- No unrelated server services or workloads are in scope.
- Never report an unrun test, unavailable Cloud check, or unmeasured capacity as passed.

---

## Historical checkpoint (pre-PR #24; retained for audit trail)

The notes below were accurate at an earlier stage and are retained as history only. Where they conflict with sections 1–5 above, sections 1–5 take precedence.


# Verigate Authority — release candidate checkpoint

Date: 2026-11-07
Repository: rudimentall1/verigate
Branch at baseline: integrate/anna-0.1.9-mainline
Baseline SHA before hardening: 5520c894313340eb47acc9e0164d5010c3ab1bb9
Current source: intentionally modified, not yet committed or pushed.

## Release identity

- Anna App candidate: 0.1.18. Server currently has 0.1.17 (ID 1981) pinned in PENDING_REVIEW; 0.1.18 has not been uploaded.
- Executa candidate: 0.1.14. Production identity cache: tool-rinat-verigate-authority-2um8gwhw; Executa identity ID 1164.
- Candidate versions are aligned in app.json, root App manifest min_version, Executa runtime VERSION, executa.json, Executa manifest, pyproject.toml, uv.lock, and binary workflow defaults.
- No Anna upload/cut/review resubmission/release or GitHub release has been performed for this candidate.

## What changed

1. Migrated Anna App manifest to schema 4; removed retired host_capabilities and method-level ui.host_api.llm/tools/storage/window declarations.
2. Added bundled verigate_ai_review. App UI -> Anna Runtime tools.invoke -> Verigate Python Executa -> protocol-v2 reverse sampling/createMessage -> Anna host LLM -> Executa result -> UI. The plugin stores no model-provider key.
3. Executa initialize advertises client_capabilities.sampling and client_capabilities.storage. One response router dispatches replies to both clients; protocol 1.1 disables both capabilities fail-closed.
4. AI remains advisory: Verigate deterministic policy owns ALLOW/WARN/BLOCK. AI can escalate ALLOW to WARN but cannot grant execution authority. Malformed responses fail closed; actual LLM outage can produce only an explicitly labelled non-authorizing policy preview.
5. Executa state path: explicit VERIGATE_ANNA_DATA_DIR, else ANNA_WORKSPACE_DIR/verigate-authority when supplied by Anna, else local-only fallback. Authoritative paths fail closed. Issuer key / SQLite cold-start initialization is locked against concurrent invokes.
6. Evidence Graph history now permits identical graph digests as distinct snapshots. Legacy SQLite UNIQUE-index migration is atomic with BEGIN IMMEDIATE and rollback; both success and injected failure rollback are tested.
7. Updated listing, README, release gate and Anna-specific threat model. Listing explicitly states this is an execution gate for the integrated Verigate App/ExecutionRouter path, not a global wallet firewall.

## Final local verification at that earlier stage

- Full Python suite: 551 passed, 4 skipped, 3 upstream deprecation warnings (117.21s), after all source/schema migration changes.
- Post-alignment contracts/protocol/binary/workspace/migration subset: 46 passed. Evidence Graph migration tests: 2 passed, including a simulated mid-migration DDL failure that proves rollback preserves the old table and data.
- Clean npm ci from package-lock.json installed 383 packages.
- Final Anna UI E2E: 38/38 passed after clean install and after final listing/security-scope edits. The real App bundle and actual Python Executa subprocess are run; only the Anna host Sampling response is mocked. No Anna CU is consumed.
- EVM atomic tests passed: stale authorization reverted with zero side effect; fresh authorization produced one side effect.
- EVM guard access-control tests passed: zero executor, attacker, stale executor state and value mismatch rejected; exact value forwarded.
- Anna CLI 0.1.64 / dispatcher 0.33.0 validate --strict: passed without warnings after final version and listing edits.
- git diff --check: passed; Git emitted only LF/CRLF normalization warnings.

## Earlier Windows artifact state (superseded by current platform-artifact evidence above)

- Executa 0.1.14 built with PyInstaller 6.22.3, packaged, extracted and passed anna/smoke_package.py after the SQLite migration change.
- Smoke covered describe, deterministic ALLOW, signed receipt, mock reverse-Sampling handshake, one-time App approval and wallet hand-off.
- Earlier Windows-only file SHA-256: f3c7c32930a00f25b7e31d9c5371d0e1167fa307a671b133240839acaa34c779. This is an earlier artifact and is not the current Windows archive hash listed in section 2.

## Earlier Anna and hackathon limitations

- Authenticated Anna CLI last showed App ID 382, status PENDING_REVIEW, pinned App 0.1.17 / version ID 1981. The in-review version predates PR #22 and this hardening.
- Anna CU quota was exhausted. No live LLM, Cloud Agent, or APS cloud acceptance was run. Local mock tests are not Cloud acceptance.
- Real Cloud install, Linux Executa discovery, server-side Sampling, host-attested App-scope APS, actual /data/workspace injection and restart/image-upgrade persistence remain unverified.
- Anna docs say ANNA_WORKSPACE_DIR maps to /data/workspace on Cloud Agents, surviving process restart, suspend/wake and image upgrades; an idle Agent/volume can be reclaimed after roughly three days. SQLite/key state is not backed up transactionally to APS yet. Do not claim indefinite durability.
- Session refresh POST /api/v1/auth/refresh -> 401 was not proven fixed.
- Native USDC wallet hand-off supports Base and Ethereum only. Solana remains policy/authorization-only.
- Security scope: this is a pre-execution gate for transactions submitted through the integrated Verigate App/ExecutionRouter. It does not intercept independent transactions sent through other wallets/clients. The current on-chain AtomicStateGuard enforces an immutable executor + atomic state/value condition, but does not independently verify the per-action Ed25519 authorization. No external independent audit or KMS/HSM integration is complete.

## Earlier next release steps (superseded by current steps above)

1. Review the entire source diff and explicitly stage only source/docs/tests; never stage .anna, node_modules, .pyinstaller or dist.
2. Commit and push a feature branch; open PR against integrate/anna-0.1.9-mainline. Require green CI on the exact commit.
3. Build and smoke all four Executa 0.1.14 platform artifacts; verify archive checksums, especially Linux x86_64 required for Anna Cloud.
4. Only after exact-SHA CI and all four artifacts pass, perform one Anna apps publish (push + immutable cut) for App 0.1.18 / Executa 0.1.14. This does not publish to Marketplace.
5. Inspect the created immutable App version and submit that exact version for Anna review / DoraHacks BUIDL. Do not call apps release until Anna approval.

Program context: DoraHacks 2349 is Anna AI App Builder Program (not PortalDot). Official qualification window ends 2026-11-30; requires approved + Marketplace-published functional App and 200 Qualified App MAU in one calendar month. The public BUIDL ID/status for Verigate was not confirmed. The user's Anna CU quota was exhausted, so live Cloud testing was not available.

Official references:
- Build on Anna 101: https://forum.anna.partners/t/build-on-anna-101/228
- Anna 1.1.0 / CLI 0.1.64 changelog: https://forum.anna.partners/t/anna-1-1-0-beta-211-beta-220-anna-ai-cli-0-1-64-permission-gates-are-gone-manifest-schema-4-shared-node-22-chrome-runtime-for-executas-async-invoke-reliability-overhaul-faster-app-opens-harness-tools-fixed/542
- Anna review timeline: https://forum.anna.partners/t/app-review-timeline-process/318
- Anna program rules: https://forum.anna.partners/t/turn-your-ai-agents-apps-into-recurring-monthly-grants-join-the-anna-ai-os-founding-builder-program-up-to-80k-month-pool/205

---

## 6. Latest session update — governed wallet enrollment + chain submission ingest

**Checkpoint refresh:** 2026-11-08 15:41 (+05:00)

This section supersedes earlier branch/worktree statements above where they conflict.

- **Current local branch:** `feat/governed-wallet-enrollment`
- **Current HEAD:** `ebf9a0ba53b31bb666b5d402efe421f1f150f351`
- **HEAD subject:** `docs: record follow-up CI and platform artifact evidence`
- **Working tree:** intentionally dirty; changes are **not committed or pushed**.
- **Latest worktree status:** modified `api/main.py`, `api/schemas.py`, `core/outcome.py`, `core/storage.py`; new `core/submission_ingest.py`, `core/wallet_enrollment.py`, `docs/WALLET-ENROLLMENT-AND-CHAIN-INGEST.md`, `scripts/chain_verifier_worker.py`, `tests/test_api_wallet_enrollment.py`, `tests/test_submission_ingest.py`, `tests/test_wallet_enrollment.py`.
- Tracked diff summary at checkpoint: 4 modified tracked files, 402 insertions / 5 deletions; untracked files are additional and are not included in that diff stat.
- `git diff --check` passed; Git emitted only LF/CRLF normalization warnings.

### What the current work is targeting

The next lifecycle gap is being addressed as a vertical slice: authenticated wallet enrollment, ingestion of wallet submission evidence, persistence of the execution receipt, and connection to the existing outcome-attestation path. The purpose is to bridge the Anna wallet hand-off to a receipt that can subsequently be checked by a separately governed chain verifier. A wallet-provided transaction hash by itself is **not** proof of on-chain success.

New/changed surfaces currently present in the worktree:
- API route/schema changes in `api/main.py` and `api/schemas.py`.
- Persistence changes in `core/storage.py`.
- Outcome lifecycle changes in `core/outcome.py`.
- New enrollment and submission-ingestion modules.
- A chain-verifier worker entry point.
- Focused regression suites for enrollment, submission ingestion and API behavior.
- Design/implementation notes in `docs/WALLET-ENROLLMENT-AND-CHAIN-INGEST.md`.

### Test evidence at this checkpoint

- Focused tests for the current lifecycle slice: **62/62 passed** (as reported in the latest run).
- Full Python suite after the current work: **581 passed, 4 skipped, 3 upstream deprecation warnings**, exit code 0, 108.85 seconds.
- These results are local test evidence only. They do not establish Anna Cloud acceptance, external RPC correctness against a live chain, or independent verifier governance.
- The previously recorded UI E2E 43/43 and EVM `test:atomic` / `test:guard` results apply to the earlier verified source state. The latest UI E2E and EVM script reruns were still pending at the time of this checkpoint refresh; do not describe them as rerun against the current dirty worktree.

### Immediate next actions

1. Finish and record the UI E2E run against this exact worktree.
2. Re-run `npm run test:atomic` and `npm run test:guard` against this exact worktree.
3. Review the complete tracked and untracked diff for trust boundaries: wallet enrollment must be authenticated and revocable; submitted tx data must be bound to the enrolled wallet/network; idempotency and replay behavior must be explicit; no caller-supplied success flag may create a confirmed outcome; the chain verifier must use a separate key/identity and trusted enrollment data.
4. Review transaction boundaries and concurrency in storage. In particular, prove that receipt creation/consumption and outcome transitions cannot be replayed or race into inconsistent states.
5. Run `git diff --check`, inspect final status, and update this checkpoint with exact test results.
6. Only then decide whether to commit/push. Do not merge, publish a GitHub Release, upload/cut App 0.1.18, or submit Anna review without explicit authorization.

### Guardrails remain unchanged

- Anna App 0.1.18 has not been uploaded/cut/submitted; preserve the last upload attempt.
- No Anna Cloud acceptance is claimed; Anna CU quota remains exhausted.
- No GitHub Release or PR merge is authorized by this work.
- Do not stage build outputs, `.anna`, `node_modules`, `.pyinstaller`, or `dist`.
- Keep all unrelated repositories, services, and workloads untouched.

## Latest authoritative update — 2026-11-08

This section supersedes the older status notes above. Older sections are retained as historical evidence only.

**Current repository state:** branch fix/anna-sampling-capability, HEAD 408a3010b31e138f627dd679ab586d7d0f79d394. Local-only edits now include anna/app.json version synchronization and these two documentation updates. No upload, immutable cut, review resubmission, App release, Executa publish, GitHub Release or PR merge occurred. Keep _tools/ and _anna-screen.png untracked.

### Anna platform

- App verigate-authority, App ID 382: immutable version 0.1.21, version ID 2048. Authenticated CLI confirms pending_review and that 0.1.21 is the pinned review candidate.
- Bundle ID 1871; 3 files; 82,794 bytes; SHA-256 manifest c54014169c50439bc7331c3d51493bf5dff8de10b67383920626b1c3b03c61fe.
- published_at is null. The App is not Marketplace-published. No apps release was run.
- Frozen dependency is production Executa tool-rinat-verigate-authority-2um8gwhw, Executa ID 1164, version 0.1.15, version ID 1029.
- Local anna/app.json was still 0.1.20 because the last bump used --no-write. It is now synchronized locally to 0.1.21 so a future patch bump starts at 0.1.22. This local metadata change does not mutate the immutable bundle or review pointer.
- CLI status and versions expose no reviewer comments. Last observed server state remains pending_review; no approval or rejection has been observed.

### Executa 0.1.15 validation

- Focused tests: 59 passed in 11.80s across test_anna_executa_manifest.py, test_anna_execution_authorization.py, test_anna_sampling_roundtrip.py and test_payee_validation.py.
- The original Windows 0.1.15 artifact cached by Anna was extracted and passed anna/smoke_package.py windows-x86_64 0.1.15. Smoke covered describe, signed ALLOW, direct privileged-call denial, one-time App approval, one-time wallet hand-off and signed SUBMITTED receipt persistence/verification.
- Original immutable Windows archive SHA-256: 57ee73192da1a75f3abae2a92ddad5bb0073a2722d19bfe5e71607d2ca22cfd6.
- Four-platform workflow 42501436184 on HEAD 408a3010 completed success. Windows x86_64, Linux x86_64, macOS ARM64 and macOS Intel each built, packaged, extracted and passed smoke. Release job skipped because publish_release=false.
- Important: the newly rebuilt CI packages are not byte-identical to the four existing immutable 0.1.15 artifacts. Do not upload these new files over 0.1.15.

| Platform | Existing immutable 0.1.15 SHA-256 | New CI 42501436184 SHA-256 |
|---|---|---|
| Windows x86_64 | 57ee73192da1a75f3abae2a92ddad5bb0073a2722d19bfe5e71607d2ca22cfd6 | eda0e70aa477936125404566617cc3ee0bef989ced2964d22e8ccf9d621e3998 |
| Linux x86_64 | b029606e0b73d5677b277bb6ee5ca3fa6ab1f5cd42155a12559eca10e272ef8e | 2284cf1a4e68c0bf0f9b8feec65f93a4e34bd4903a70bdab0f698bb437d08b18 |
| macOS ARM64 | 08a4d3229c9ce467114abebf8f9609c459a1c6789056ee0a7e6a4c36a3bf0904 | 5dbd0abce88361219647eec87ac415266627124d8ac21dd7234a54aa35071366 |
| macOS Intel x86_64 | c9811701b250f7b95eca5c43af3325c4295564918bfc4ec881f65adfa42f8231 | 227a4209ba5c25c864a888d3374151599b2a6cfde76dc126522584fd4b56c5c8 |

- Executable payloads inside all four new packages also differ; this is not only an outer archive metadata difference. On Windows the PE timestamp differs. The audited plugin/build inputs and Windows build dependency versions (Python 3.11.9, PyInstaller 6.22.3, cryptography 50.0.2) were the same in both workflow runs. This proves a reproducible-build gap, not a source regression.
- For a future Executa release, set deterministic PyInstaller inputs (PYTHONHASHSEED and SOURCE_DATE_EPOCH), normalize archive metadata, and compare repeated builds from the same commit for all four targets. PyInstaller guidance: https://pyinstaller.org/en/v6.12.0/advanced-topics.html. Do not spend a new immutable version just to fix hashes.
- Keep the new downloaded CI packages in %TEMP%\verigate-ci-42501436184, not in the repository. The original immutable 0.1.15 packages remain the artifacts frozen by Anna App 0.1.21.

### App verification and limits

- Previously verified local full Python suite after App hardening: 621 passed, 4 skipped. Anna UI E2E: 53/53 passed. These are local tests, not Cloud acceptance.
- Main CI run 42499285025 passed contracts, test and anna-ui.
- Sampling round-trip used a fixture-backed host response. It does not prove a real Anna Cloud LLM response.
- Real Anna Cloud Sampling, platform permission grant, APS persistence/restart and Cloud Agent installation remain unverified because Anna CU quota is exhausted. Do not call Anna Cloud LLM/Sampling or claim live end-to-end AI acceptance.
- Wallet submission receipt is a signed SUBMITTED executor self-report after a wallet hash return; it is not on-chain confirmation. Governed CHAIN_VERIFIER finality/outcome/reorg handling is not integrated into the standard Anna UI path.

### Next actions

1. Preserve App 0.1.21 as the pinned review candidate. No new App cut or release while review is pending and no reviewer feedback is available.
2. Do not modify or overwrite Executa 0.1.15 with the mismatching new CI artifacts.
3. Before a future Executa version, fix reproducibility and compare two builds of the same commit on all four targets.
4. If reviewers return actionable feedback, patch once, run full Python and UI E2E, inspect the diff, then create one App 0.1.22 and submit that exact version. Keep Cloud limitations explicit.

## Build reproducibility hardening — local changes, not yet in CI

- Updated `anna/package_binary.py` to write deterministic ZIP and TAR.GZ archives: stable entry order, fixed timestamps derived from `SOURCE_DATE_EPOCH`, fixed owner/group IDs and names, normalized modes, no ZIP extra/comment fields, fixed gzip timestamp, and stable compression settings.
- Updated `.github/workflows/anna-executa-binaries.yml` to export `PYTHONHASHSEED=0` and `SOURCE_DATE_EPOCH` from the checked-out commit timestamp. Added `anna/verify_reproducible_binary.py`: every native CI runner now runs two complete PyInstaller builds and compares SHA-256 before packaging/smoke. A mismatch fails the job. PyInstaller documents these deterministic build controls: https://pyinstaller.org/en/latest/advanced-topics.html.
- Added reproducibility tests for ZIP and TAR.GZ packaging. The tests change source file mtimes between package runs and assert the resulting archive bytes are identical and member metadata is normalized.
- Packaging tests + reproducibility-gate tests + smoke-package parser + Executa manifest/auth/Sampling/payee regression set: **74 passed**. Workflow YAML parse: PASS.
- Full Python suite on the final modified worktree: **626 passed, 4 skipped, 3 upstream deprecation warnings**.
- Local Windows full PyInstaller build was run twice with the same environment: Python 3.10.11, PyInstaller 6.22.3, `PYTHONHASHSEED=0`, `SOURCE_DATE_EPOCH=1794154754`. Both EXE files had identical SHA-256: `91d17be5a61d4a7206bb7fdada5bf3c87be1cec70e25526255ff6b57ec148191`.
- A fresh Windows deterministic build then passed `anna/smoke_binary.py <exe> 0.1.15`: describe, signed ALLOW, App-scope approval once, wallet hand-off once, and SUBMITTED receipt persisted/verified.
- Scope limitation: this is local Windows reproducibility evidence. The new workflow changes have **not** been pushed or run on Linux/macOS yet. Repeat-build equality on Linux x86_64, macOS ARM64 and macOS Intel remains unverified.
- Existing immutable 0.1.15 platform artifacts and Anna's frozen dependency were not overwritten. The old published hashes remain authoritative; new rebuilds must not be uploaded over version 0.1.15.
- Local modifications remain uncommitted/unpushed. No immutable Executa version, App version, GitHub Release, review submission or Marketplace release was created.


## Cross-platform CI verification gate added — 2026-11-08

- Workflow no longer builds an Executa binary only once. Each native matrix runner now invokes `anna/verify_reproducible_binary.py`, which runs `anna/build_binary.py` twice with the same fixed environment, computes SHA-256 after each full build, and fails closed if they differ. Only after equality does the workflow package and smoke-test the executable.
- Added regression coverage for missing reproducibility environment, successful equal-hash verification, and mismatch rejection.
- Final focused regression set: **74 passed**. Full Python suite: **626 passed, 4 skipped, 3 upstream deprecation warnings**.
- This cross-platform gate is now in the workflow source but is not yet validated by GitHub Actions. CI must run on Windows, Linux, macOS ARM64 and macOS Intel after push.
- Local Windows two-build equality remains: SHA-256 `91d17be5a61d4a7206bb7fdada5bf3c87be1cec70e25526255ff6b57ec148191`; fresh executable smoke passed.


## Four-platform reproducibility CI — final result 2026-11-08

<badge>CI SUCCESS</badge> Run [42504828571](https://github.com/rudimentall1/verigate/actions/runs/42504828571), commit `9182b06431d33e5dac8fd666b98db6248cfeffa4`, branch `fix/anna-sampling-capability`.

All four native platform jobs completed success. Each runner executed the full PyInstaller build twice with identical environment, compared binary SHA-256, then packaged, extracted and smoke-tested the archive.

| Platform | Binary SHA-256 (build 1 = build 2) | Job result |
|---|---|---|
| Windows x86_64 | `316edcfade757c29161b6882f6c2479740bbc6df8f719355e9bbf5df6e878938` | PASS |
| Linux x86_64 | `9d4d4b26cbe05b8a2e81eb8def0413c82253d9df1c6879495895ce9c55b3f7b6` | PASS |
| macOS ARM64 | `ea0917c6f9900f5fcde46c943a4e97bb42ca70d71a34144b7e67e06919ef37bc` | PASS |
| macOS Intel x86_64 | `2e2551a56583ecf59e6b23098fc1d3cad8d89d253550083bba10a351e218f09b` | PASS |

- Four non-expired workflow artifacts are present: `verigate-authority-windows-x86_64`, `verigate-authority-linux-x86_64`, `verigate-authority-darwin-arm64`, `verigate-authority-darwin-x86_64`.
- Workflow overall conclusion: **success**. The separate GitHub `release` job is **skipped** because `publish_release=false`.
- These are CI artifacts only. No GitHub Release, no Executa publish/update, no Anna App cut, no review resubmission and no Marketplace release occurred.
- Do not upload the new artifacts over immutable Executa 0.1.15. Anna has the exact previously-published 0.1.15 artifacts cached; the new workflow outputs have not been compared against each of those four immutable artifact hashes in this final run. The review App 0.1.21 remains frozen to production Executa 0.1.15.
- Final local full Python suite on this source: **626 passed, 4 skipped, 3 upstream deprecation warnings**. Focused reproducibility/package/auth set: **74 passed**. Anna strict manifest validation and workflow YAML parsing passed before push.
- Pushed commit: `9182b06431d33e5dac8fd666b98db6248cfeffa4`, message `build: enforce reproducible Executa artifacts`. Branch is pushed; local untracked `_tools/` and `_anna-screen.png` remain excluded.

**Decision:** the reproducible-build fix is verified on all four target platforms. Executa 0.1.15 remains immutable. No new version is needed merely to apply this build-system fix; use a new Executa version only if a separately tested runtime change is required.
## Anna App 851 — Sampling error-envelope fix and release 0.1.23 — 2026-11-09

### Bug found from user test evidence
- User's five App test runs all showed the same behavior: extracted fields remained empty/default placeholders (recipient `0x…`, amount `25`, resource `Invoice 1042`) and UI reported "Anna AI could not read the request. No check was run."
- Root cause in `anna/bundle/app.js`: `askAnna()` only classified reverse-Sampling failures as eligible for policy-only fallback when the Executa error explicitly carried `llm_available: false`. If Anna wrapped the failure in an error envelope without that marker, the UI stopped before deterministic extraction and `verigate_check`.
- Narrow fix: normalize error details from `outer.error`, `outer.data.error`, and outer status/code; classify known Sampling/quota errors as degraded-mode candidates; keep HTTP 401/403, auth/session, ownership and missing-Executa errors as hard failures. The degraded path uses only explicit, unambiguous payment values, is labelled policy-only, and cannot issue execution authorization.
- Added UI regression cases covering a Sampling rejection envelope without `llm_available` and a 401 error envelope. The former reaches the deterministic policy preview with execution disabled; the latter fails closed before policy evaluation.

### Validation
- Full local Anna UI E2E after patch: **55/55 passed**, exit 0. Harness runs real bundled UI + real local Executa plugin with a mocked Anna host; this is not live Anna Cloud acceptance.
- Targeted regression: Sampling error envelope **1/1 passed**; AI 401 error envelope **1/1 passed**.
- `anna validate --strict`: passed.
- `git diff --check`: passed before App metadata bump; rerun after checkpoint update.
- Live Anna Cloud reverse Sampling / account grant / current quota remains **unverified**. Do not claim the host LLM is working until tested in the actual App runtime.

### New Anna account upload
- App ID **851**, slug `verigate-authority`, immutable App version **0.1.23**, version ID **2071**.
- Bundle ID **1891**, 3 files, **83,683 bytes**, SHA-256 manifest `6fee7f0b5a2ee9d1c6bdfa53f7b7897c213a7227661ae1c58b2558fe5358ca4e`.
- Frozen bundled Executa remains Tool ID `tool-verigate-authority-verigate-authority-28x5jku8`, Executa ID **1314**, version **0.1.16**, version ID **1042**.
- Current platform status: App `draft`, `is_published=false`, no review candidate, no review submission, no Marketplace publication.
- Prior App versions 0.1.21 / 0.1.22 retained. Old account App ID 382 untouched.
- Local source files changed for this fix: `anna/bundle/app.js`, `scripts/test_anna_ui.mjs`, `anna/app.json`, and this checkpoint. Do not stage `_tools/` or `_anna-screen.png`.

**Next test in Anna:** reopen/refresh App 0.1.23 and submit a single explicit payment sentence including the network, e.g. `Pay 25 USDC on Base to 0x5aAeb6053F3E94C9b9A09f33669435E7Ef1BeAed for invoice 1042.` If Sampling is unavailable but explicit details parse, expect a clearly labelled policy-only result with execution authorization disabled. This is not an end-to-end live LLM pass until Anna Cloud returns a successful Sampling response.
