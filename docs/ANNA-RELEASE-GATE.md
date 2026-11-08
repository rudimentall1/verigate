# Verigate Authority — Anna release gate

## Current candidate status - 2026-11-08 (authoritative override)

This block supersedes older branch names, SHA values, checkout descriptions, test counts and artifact status in the historical baseline below. Do not use historical CI or binary builds as proof for the current uncommitted worktree.

- Repository: rudimentall1/verigate; branch: feat/anna-0.1.18-executa-0.1.14-hardening.
- Current HEAD: 70c52f05cf36c0d8e9bb436c0edb913c62fbcd84 (fix: mark platform-specific fsevents as optional). PR #24 is OPEN and not merged. The worktree has 22 modified, uncommitted files; no files are staged, no new commit or push has been made.
- Candidate versions remain App 0.1.18 / Executa 0.1.14. No Anna upload, cut, publish, review submission, Marketplace release or GitHub Release has been made.
- Latest full Python suite on the current source: 578 passed, 4 skipped, 3 upstream deprecation warnings (112.73s).
- Latest Anna App UI E2E: 43/43 passed (183.24s), using the real local App bundle and Python Executa subprocess with fixture-backed Anna host calls. This is not Anna Cloud acceptance.
- Local policy and identity tests cover 50 different Agent labels sharing one issuer-installation principal and blocking the 51st 40-USDC request at the 2,000-USDC rolling cap. Two separate two-connection concurrency regressions cover ordinary payment evaluation and WARN-review authorization; only one of two concurrent final 40-USDC requests is allowed.
- EVM chain/RPC/outcome/lifecycle focused tests: 24/24 passed. The verifier checks signed transaction binding, requires the observed transaction chainId, checks verifier-pinned enrolled sender, tx/receipt block metadata, canonical block hash and configured confirmation depth. It is not wired into Anna's UI and does not issue an independent CHAIN_VERIFIER attestation.
- npm run test:atomic passed: stale authorization reverted, stale side effect 0, fresh side effect 1. npm run test:guard passed: zero executor, attacker/oracle, stale state and value mismatch rejected; exact value forwarded. Ganache used the NodeJS fallback because the optional ?WS native binary is absent on this Windows/Node build.
- Anna schema-4 validation passed with @anna-ai/cli@0.1.64 / dispatcher 0.33.0 using validate --strict.
- Existing exact-SHA GitHub CI and four-platform Executa artifacts are for the prior committed HEAD only. Existing archives were built before the current 22 local edits and are NOT final candidate binaries. Rebuild all four platforms from the eventual candidate commit and require green CI on that exact SHA.
- Anna CU quota is exhausted. Real Cloud Agent install, LLM Sampling, APS App-scope authorization, /data/workspace persistence/restart and post-upgrade lifecycle remain UNVERIFIED.
- Remaining release blockers: signed SUBMITTED ExecutionReceipt persistence from wallet send; separate governed CHAIN_VERIFIER service/key and independent OutcomeAttestation; wallet enrollment registry mapped to an authenticated principal; network-specific finality plus post-attestation reorg monitoring/reversal; cross-Agent/account-wide budget across separate workspaces; realistic multi-process/Executa load test.
- Payment values are arbitrary positive USDC values with up to six decimals; 50 and 250 are policy thresholds, not allowed denominations. Static per-transaction cap is 500 USDC and rolling daily cap is 2,000 USDC (hard BLOCK); effective PROBATION dynamic ceiling is currently 50 USDC.
- RELEASE DECISION: not ready for Anna upload/cut. Continue source-level work, then final review, commit/push the feature branch, run exact-SHA CI and rebuild binaries. Do not use the last upload attempt as a debugging experiment.



## Historical baseline - 2026-11-07

This working checkpoint supersedes the earlier baseline notes after local hardening against the official Anna 1.1.0 / CLI 0.1.64 documentation published 2026-11-06. Source changes are currently uncommitted on the Windows laptop; the candidate SHA, CI and binary artefacts must be recorded only after the final local suite and a single reviewed Git commit. A green source build is not the same as a successful Cloud Agent install, Marketplace approval, or publication.

### Source and local checkout

- Repository: [rudimentall1/verigate](https://github.com/rudimentall1/verigate).
- Working branch: `integrate/anna-0.1.9-mainline`.
- Baseline commit before this hardening pass: `5520c894313340eb47acc9e0164d5010c3ab1bb9`. The current local candidate is uncommitted; its SHA does not exist yet. The earlier signed merge commit `d79d660e08314a4e75aba23319967047f7e80dcb` and docs merge `5520c894...` are historical baselines, not the new release candidate.
- PR [#22](https://github.com/rudimentall1/verigate/pull/22) is merged. It adds policy-only preview after an actual Host LLM invocation failure, uses only explicit form values, discloses that contextual AI review did not run, keeps execution permission disabled, and rejects malformed LLM response data rather than treating it as an outage.
- The Windows checkout at `C:\Users\User\Desktop\Work\verigate-anna-0.1.13` was initially detached at `addef3a`. Its worktree was clean; it was switched to `integrate/anna-0.1.9-mainline` and fast-forwarded to the verified merge commit. Final status was clean and matched `origin/integrate/anna-0.1.9-mainline`.
- Local laptop toolchain observed during hardening: Python `3.10.11`, Node.js `v24.18.0`, npm `11.16.0`, `@anna-ai/cli` `0.1.64`, app-schema dispatcher `0.33.0`.
- The Windows worktree started clean at `5520c894313340eb47acc9e0164d5010c3ab1bb9`. It is now intentionally modified and uncommitted; do not treat the old merge SHA or old CI as validation of these changes.
- `anna-app validate --strict` passed against schema-4 `anna/manifest.json` with CLI `0.1.64` and no warnings. This validates the App manifest, not Cloud install/runtime.

### CI and Executa artifacts

- CI run [42353190020](https://github.com/rudimentall1/verigate/actions/runs/42353190020) passed on the exact merge commit. Jobs: `anna-ui`, `test`, and `contracts`.
- Binary workflow [42353190033](https://github.com/rudimentall1/verigate/actions/runs/42353190033) passed on the exact merge commit. Linux x86_64, Windows x86_64, macOS ARM64 and macOS Intel x86_64 all built, packaged, extracted and smoke-tested successfully. The workflow's draft-release job also completed successfully.
- Historical GitHub Executa release `0.1.13` was a draft and `0.1.12` the published version when last checked. Neither proves the new candidate. No new GitHub Release or Anna upload has yet been made.
- Current local candidate versions are App `0.1.18` and Executa `0.1.14`, aligned across `app.json`, root App manifest `min_version`, `executa.json`, runtime `VERSION`, Executa `manifest.json`, `pyproject.toml`, `uv.lock` and binary workflow defaults. The production identity is cached in `anna/.anna/executas.lock.json` as `tool-rinat-verigate-authority-2um8gwhw`; Executa identity ID `1164`; `tool-dev-verigate-authority` remains the local dev fallback.
- Windows x86_64 `0.1.14` was built locally with PyInstaller 6.22.3, packaged, extracted and smoke-tested successfully. SHA-256: `f3c7c32930a00f25b7e31d9c5371d0e1167fa307a671b133240839acaa34c779`. Linux x86_64, macOS ARM64 and macOS Intel artifacts for `0.1.14` are **not built yet**.

### Authenticated Anna Developer state

Read through the locally authenticated `anna-app` CLI (host `https://anna.partners`):

- App: `Verigate Authority`, slug `verigate-authority`, ID `382`.
- App status: `PENDING_REVIEW`.
- Latest immutable App version: `0.1.17`, ID `1981`; this exact version is pinned as the current review candidate.
- CLI reports 16 immutable versions. The versions listing reports `published=—` for all listed versions; no Marketplace-published version was shown.
- The local, not-yet-uploaded candidate is `anna/app.json` `0.1.18`, following the server's pinned `0.1.17`. The server still retains `0.1.17`; no candidate upload was performed.
- App `0.1.17` predates merge commit `d79d660e` and therefore does **not** contain the PR #22 UI fallback changes. Do not describe the in-review version as containing those changes.
- Previous dry-runs for the old 0.1.15/0.1.13 candidate were read-only and are not evidence for the new content. The current `0.1.18`/`0.1.14` candidate has not yet been submitted to Anna CLI; no `apps push`, `apps cut`, `apps publish`, `apps submit-review` or `apps release` operation has been performed in this hardening pass.
- CLI help confirms: `apps publish` is the composite `push + cut`; it does **not** publish to the Marketplace. `apps submit-review` pins a review candidate; `apps release <version>` is the later go-live operation after approval. A new cut during an active review does not replace the pinned review candidate until review is explicitly re-submitted.
- The CLI's `apps grants` command returned “no grants endpoint data available”; this is not evidence of a grant or of MAU performance.

### Local release verification — current source candidate (Windows laptop)

- A real Anna Cloud Agent install, Executa discovery and repeated invocation have not been demonstrated; the Anna CU quota is exhausted, so they cannot be run in this pass.
- The real browser/session refresh failure `POST /api/v1/auth/refresh → 401` has not been proven fixed. PR #22 tests safe fallback behavior in scripted runtime; it does not prove that a genuinely expired Anna session still permits Host tool invocation.
- The plugin's current source now negotiates Executa protocol v2 and explicitly advertises both `client_capabilities.storage = {}` and `client_capabilities.sampling = {}`. The latter is required for Anna reverse LLM sampling; the former is required for APS. The one-time approval path uses App-scoped APS KV via host-attested owning-App invocation and ETag-conditional deletion.
- The App manifest is now schema 4; retired `host_capabilities` and method-level `ui.host_api.llm/tools/storage/window` declarations have been removed. CLI `0.1.64 validate --strict` passes without legacy-field warnings.
- AI interpretation and contextual risk review now use the complete Anna path: App UI → `anna.tools.invoke` → bundled Verigate Python Executa → `sampling/createMessage` reverse RPC → Anna host LLM → Executa response → App UI. Policy evaluation and final ALLOW/WARN/BLOCK remain deterministic inside Verigate. This is covered by a local protocol wire round-trip test and by the UI harness, where the real plugin subprocess answers a mock host Sampling request. No Anna CU is spent in those tests.
- Current Anna APS documentation says protocol v2 is the access gate: the host mints a storage token for each invocation of an installed, enabled Executa, and App scope is available only for a host-attested invocation originating from the owning App context. Legacy Executa `host_capabilities` entries such as `aps.scope.app.read/write` are ignored; they must not be represented as the actual grant mechanism. Do not assume a separate storage-permission toggle without observing the current runtime.
- APS KV/object storage is not a transactional relational database. The policy/accounting SQLite database and Ed25519 issuer keypair resolve to `VERIGATE_ANNA_DATA_DIR` when explicitly set; otherwise to `ANNA_WORKSPACE_DIR/verigate-authority` when Anna injects it; local-only fallbacks are considered only when neither variable is present. Explicit override and Anna workspace are authoritative and fail closed when unavailable. Tests cover both selections and failure without fallback.
- Current Anna docs describe `ANNA_WORKSPACE_DIR` as `/data/workspace` on Cloud Agents. The volume survives process restart, suspend/wake and image upgrades, but Anna may reclaim a fully dormant Cloud Agent and its volume after about three days. Durable authoritative records must be checkpointed to APS; SQLite/issuer-key persistence across real lifecycle events has not been verified because the Anna CU quota is exhausted.
- Do not mirror a live SQLite file to APS Files and call it transactional durability. Durable accounting requires a transactional persistent store or a platform-backed persistent volume with documented single-writer/atomicity guarantees; signing-key identity and replay/accounting state must survive the supported lifecycle.
- Final full Python suite after the `0.1.18` / `0.1.14` alignment and atomic SQLite migration hardening: `551 passed, 4 skipped` (3 upstream deprecation warnings; 117.21s).
- After clean `npm ci`: Anna UI flow suite `38/38 passed`; EVM atomic test passed (stale authorization reverted, stale side effect `0`, fresh side effect `1`); EVM guard test passed (zero executor, attacker, stale state and value mismatch rejected; exact value forwarded).
- `anna-app validate --strict` with CLI `0.1.64` / dispatcher `0.33.0` passed after version alignment and final listing changes, without warnings.
- Final Windows frozen Executa `0.1.14` was rebuilt after atomic SQLite migration hardening; the extracted ZIP passed `anna/smoke_package.py`, including reverse-Sampling mock handshake and approval/wallet smoke. SHA-256 verified from disk: `f3c7c32930a00f25b7e31d9c5371d0e1167fa307a671b133240839acaa34c779`.
- `git diff --check` passed (only CRLF normalization warnings).
- **Still pending:** final source diff review, commit and push; green GitHub CI on the exact new commit; Linux/macOS builds and smoke packages.
- **Cloud acceptance remains unverified and cannot be run with the current exhausted Anna CU quota.** Local host fixtures prove protocol and code paths only; they cannot prove Cloud Agent installation, server-side Sampling enablement, APS App-context issuance, Linux binary discovery, or `/data/workspace` lifecycle behaviour. Do not mark this App Anna-ready or claim a successful Cloud Agent test.

### Anna accounting identity boundary ? local hardening, limited scope

The current source maps every user-provided agent_id label to a server-derived principal based on the persistent Ed25519 issuer public-key fingerprint. Policy previews, capability IDs, persistent spend/rate accounting and dynamic authority all use this principal. The signed label is retained for display and exact App/UI binding. This closes label rotation within one issuer installation.

This is not a cross-Agent/account-wide limit: separate Anna Agent workspaces or App installations with separate issuer keys have separate principals. Multiple logical agents on one installation currently share one budget. A true per-agent model requires cryptographic enrollment; a cross-Agent account budget requires a trusted platform identity and a concurrency-safe shared ledger. APS KV currently has ETag CAS for existing records but no atomic create-if-absent for race-free first bootstrap. The real Cloud Agent workspace/key persistence has not been verified because Anna CU quota is exhausted. Do not claim a Cloud or account-wide guarantee.

### Program context — keep separate from PortalDot

DoraHacks hackathon **2349** is the **Anna AI App Builder Program**, not the separate PortalDot hackathon. The official Anna Founding Builder rules set the initial qualification window to 2026-09-01 through 2026-11-30. Qualification requires an approved and Marketplace-published functional App plus at least 200 Qualified App MAU in one calendar month during that window. For October/November first qualification, the standard Tier E grant at 200 MAU is $50/month; September-only launch-boost amounts no longer apply. Developer/internal QA, bots, failed/cancelled/incomplete runs and meaningless incentivized traffic do not count. See the [official Anna program rules](https://forum.anna.partners/t/turn-your-ai-agents-apps-into-recurring-monthly-grants-join-the-anna-ai-os-founding-builder-program-up-to-80k-month-pool/205).
The user's public DoraHacks submission ID/status for this program has not been independently confirmed. The separate PortalDot deadline described in the prior checkpoint was 2026-11-06 and must not be conflated with hackathon 2349.

### Next release discipline

1. Finish the post-version-bump targeted/full local tests and inspect the complete Git diff; do not use historical CI as proof for this candidate.
2. Commit and push the release candidate. Require green CI on that exact SHA, including `anna-ui`, Python/contracts and all four Executa binary build/package/smoke jobs.
3. Retrieve and verify Linux x86_64, macOS ARM64 and macOS Intel `0.1.14` archives plus checksums; Windows is already locally smoke-tested.
4. Only then perform the single Anna `apps publish`/push+cut for App `0.1.18` with Executa `0.1.14`. The account's CU quota is exhausted, so there will be no exploratory Cloud LLM test; disclose this limitation to reviewers. Do not run multiple trial uploads.
5. Inspect the exact created version and only then submit the candidate for Anna review / DoraHacks BUIDL. Marketplace approval and `apps release` are separate later actions; no public release is implied by an upload or green CI.

Reference: [Anna Forum — Build on Anna 101](https://forum.anna.partners/t/build-on-anna-101/228), [Anna developer docs](https://github.com/Anna-Partners/anna-developer-docs).

This gate prevents incremental Marketplace uploads. A candidate is not Anna-ready merely because the Python suite, UI mock, local strict validation or CI passes.

## 1. Source and protocol consistency

- [x] `app.json` bundled handle resolves to the actual Executa directory.
- [x] Schema-4 root App manifest allow-lists the bundled Executa in `required_executas`; retired method-level `ui.host_api` ACLs are absent.
- [x] Every method invoked by `bundle/app.js` exists in the Executa `describe` manifest.
- [x] Every method's parameter names, types and required flags match its implementation.
- [x] Executa identity and version agree across `executa.json`, the Python plugin and its `describe` response.
- [x] The active distribution profile is the intended release profile and includes `linux-x86_64` for Anna Cloud Agent.
- [x] Windows x86_64 0.1.14 archive entrypoint, archive-root manifest, SHA-256 and extracted EXE passed the local package smoke suite.
- [ ] Linux x86_64, macOS ARM64 and macOS Intel 0.1.14 archives must be built and smoke-tested on GitHub Actions before the App upload.

## 2. Deterministic authority and cryptography

- [x] ALLOW, WARN and BLOCK are produced by the deterministic policy engine, never by Anna's LLM.
- [x] AI risk flags can escalate ALLOW to WARN but cannot downgrade WARN or BLOCK.
- [x] Missing or ambiguous fields stop before policy invocation.
- [x] Every Decision Receipt is verified before any decision is displayed, including fresh decisions returned during execution authorization.
- [x] Every Execution Authorization is signature-verified, unexpired, and bound to the installation principal, signed display label, exact action, target, amount, asset, network and resource shown in the UI.
- [x] Rotating the caller-supplied Agent label cannot reset spend/rate/dynamic-authority state within one issuer installation; a local regression reaches the 2,000-USDC daily cap through 50 unique labels and BLOCKs the next attempt.
- [x] Missing keys, malformed responses, invalid signatures and unexpected response envelopes fail closed without displaying a decision or permission.
- [x] Issuer private keys are stored with POSIX mode 0600 inside a mode-0700 app data directory; legacy permissions are tightened and symlinked key paths are rejected.

## 3. Execution boundary

- [x] A preview check is non-persistent and never submits a transaction.
- [x] Execution Authorization is issued only after a separate explicit user confirmation and a fresh persistent policy check returns ALLOW.
- [x] Direct model/tool invocation without a UI-created approval record is rejected both outside App context and when App context exists; no client-supplied boolean can mint approval.
- [x] Both privileged methods require separate 60-second App-scope approvals: one bound to the exact payment before issuing Execution Authorization, and one bound to the exact authorization ID and transaction before ExecutionRouter consumption. Each record is ETag-deleted exactly once.
- [x] Critical approvals use the in-App dialog rather than browser `window.confirm()`; dialog cancellation writes no approval record and does not consume an existing permission.
- [x] WARN can receive execution authority only after a distinct App-scope one-time review bound to the exact WARN rule IDs and payment; fresh policy/capability/dynamic authority are rechecked. BLOCK and hard budget/cap rules are never overridable.
- [x] The wallet path is limited to the explicitly supported native-USDC networks.
- [x] The exact signed transaction is reconstructed and compared before wallet submission.
- [x] ExecutionRouter consumes the one-time authorization before the wallet is asked to sign.
- [x] Replay of a consumed authorization is rejected.
- [ ] Wallet submission tx hash is persisted as a signed SUBMITTED ExecutionReceipt and bound to the enrolled wallet sender.
- [ ] A separately governed CHAIN_VERIFIER confirms canonical block/finality and issues an independently signed outcome attestation before dynamic authority can progress.
- [ ] Reorg monitoring/reversal is defined and tested for any previously attested transaction.
- [x] Wallet rejection, account changes, chain changes and post-consumption failures are reported without suggesting that funds were sent.

## 4. Automated release checks

Required before a candidate can be called source-ready:

- [x] Latest full Python unit and integration suite on current uncommitted source: 577 passed, 4 skipped, 3 upstream deprecation warnings (120.52s).
- [x] Evidence Graph migration tests: 2 passed, including an injected table-creation failure proving DDL rollback preserves the prior schema and data.
- [x] Contract and ExecutionRouter EVM end-to-end suites passed locally on Ganache.
- [x] Latest Anna UI E2E against the real bundle and Python Executa process with fixture-backed reverse-Sampling/APS host: 43/43 passed (183.24s).
- [x] Cross-layer App/Executa/manifest contract tests passed after the 0.1.18/0.1.14 alignment; exact candidate CI remains required.
- [ ] Rebuild/package/smoke Linux x86_64, Windows x86_64, macOS ARM64 and macOS Intel from the final candidate commit. Artifacts built from prior HEAD are stale for this worktree.
- [x] `anna-app validate --strict` on schema 4 / CLI 0.1.64 passed after SemVer alignment and listing changes without warnings.
- [ ] The final CI run must be green on the exact candidate commit. No candidate commit or CI run exists yet.

## 5. Real Anna acceptance — one consolidated pass

Real Anna Cloud Agent acceptance is currently unavailable because the Anna CU quota is exhausted. The following matrix remains unverified and must not be represented as passed. If quota is restored, install one candidate in a test Agent and run this matrix before claiming Cloud-ready. Do not publish successive fixes one by one.

| Scenario | Required outcome |
|---|---|
| Small valid Base USDC request | ALLOW; valid signed receipt; no transaction sent |
| Amount above human-review threshold | WARN; valid receipt; no execution permission |
| Amount above hard cap | BLOCK; valid receipt; no execution permission |
| Malformed recipient | BLOCK; valid receipt |
| Prompt-injection / bypass language | At least WARN; never ALLOW solely because of model text |
| Missing or ambiguous amount/recipient | Clarification; no policy call until resolved |
| Tampered Decision Receipt | No decision displayed |
| Tampered or mismatched Execution Authorization | No permission displayed and no wallet call |
| Replayed consumed authorization | Rejected by ExecutionRouter |
| Wallet sends an EVM transaction | A signed SUBMITTED ExecutionReceipt is persisted with the exact tx hash and enrolled wallet binding |
| EVM transaction remains pending / shallow / reorged | Outcome stays UNKNOWN; no dynamic-authority promotion |
| EVM transaction reaches configured finality threshold | Separate governed CHAIN_VERIFIER confirms exact tx/receipt/effect and emits an independently signed OutcomeAttestation |
| CHAIN_VERIFIER attestation replay/tampering/wrong wallet | Rejected against registered verifier key, stored signed receipt, exact action, enrolled sender and canonical block evidence |
| Post-attestation reorg | Reorg monitor emits a governed adverse/reversal event or freezes progression; no automatic success assumption |
| Tool unavailable / bad envelope / missing issuer key | Clear fail-closed error; no decision inferred |

The real Anna acceptance pass must record the exact App version, Executa version, Agent type (Cloud or local), tool handle resolution, test results and relevant error text. Never infer cloud compatibility from local jsdom tests.

## 6. Additional Anna platform guidance — 2026-11-07

Reviewed the official founder/developer sources directly from Anna Forum and the current developer documentation:
- [Build on Anna 101](https://forum.anna.partners/t/build-on-anna-101/228): local harness, UI/Executa responsibilities, reverse Sampling chain, Bundled Executa handles, binary build, and the distinct real Cloud Agent acceptance requirement.
- [Anna 1.1.0 / CLI 0.1.64 changelog](https://forum.anna.partners/t/anna-1-1-0-beta-211-beta-220-anna-ai-cli-0-1-64-permission-gates-are-gone-manifest-schema-4-shared-node-22-chrome-runtime-for-executas-async-invoke-reliability-overhaul-faster-app-opens-harness-tools-fixed/542): manifest schema 4, retired method ACLs and host_capabilities, current Host/Executa contract.
- [APS getting started](https://forum.anna.partners/t/getting-started-with-anna-aps-save-files-find-them-again-and-know-when-to-use-upload/437): KV vs Files and scope behaviour.
- [APS / host capability corrections](https://forum.anna.partners/t/docs-corrections-host-capabilities-aps-scopes-and-a-few-things-that-cost-me-a-day/248): legacy scope declarations and owning-App context caveats.
- [Anna developer docs index](https://anna.partners/llms.txt) and full developer corpus (`https://anna.partners/llms-full.txt`).

### Executa protocol — source review passed; Cloud remains unverified

- [x] App bundle uses the CLI-generated `window.__ANNA_TOOL_IDS__` mapping with a development fallback.
- [x] `describe` returns the tool manifest directly in JSON-RPC `result`; no extra `manifest` or business-result wrapper.
- [x] Tool parameter declarations use the required list-of-objects format and supported types.
- [x] `initialize` negotiates protocol v2 and advertises both `client_capabilities.storage` and `client_capabilities.sampling`.
- [x] The process keeps reading stdin after `describe`, correlates both APS and Sampling reverse-RPC responses through one router, and returns one JSON-RPC response per line.
- [x] A local wire-level test performs a complete `invoke -> sampling/createMessage -> host reply -> invoke result` cycle and verifies `context.invoke_id` propagation.
- [x] The Anna UI E2E harness runs the actual bundle and Python Executa subprocess with a fixture-backed mock Sampling host; it does not call Anna's paid LLM service.
- [x] Linux, Windows, macOS ARM64 and macOS Intel binaries passed the current smoke-test workflow.
- [ ] Actual install, tool discovery and repeated invocation on a real Anna Cloud Agent remain unverified.

### Agent Session — deliberately not required for this release

The current payment intake uses bounded Anna host LLM calls through Executa protocol-v2 Sampling: one for request interpretation/contextual risk review and one for explaining the deterministic decision. Missing or ambiguous details are shown as form questions; the user edits the form and starts a fresh check. It does not promise a persistent chat conversation, so stateless reverse Sampling is sufficient for this interaction model. The model has no privileged authorization or wallet-consumption path.

- [x] No automatic Agent Session or Agent tool-routing permission is enabled.
- [ ] A future conversational intake upgrade may adopt Agent Session for follow-up context, streaming, cancellation and refresh recovery.
- [ ] If adopted, create one Session per conversation, restore it by saved session UUID, and use `quotaCaps.allowed_tools: []` for the intake model. The LLM must never receive a path to privileged Verigate authorization or wallet-consumption methods; only explicit App UI buttons may invoke those methods.

### APS — code path present; Cloud invocation/persistence unverified

- [x] App UI writes only a short-lived unique approval record in the private `app` KV scope.
- [x] The bundled Executa reads the approval, validates its nonce, exact action binding and 60-second expiry, then consumes it with ETag-conditional delete.
- [x] The Executa negotiates protocol v2 and advertises `client_capabilities.storage` and `client_capabilities.sampling`. It uses App-context reverse RPC for the short-lived approval record. Legacy `host_capabilities` strings in the Executa manifest are ignored by the current Anna runtime and are not an authorization grant.
- [x] Host Upload is not used as a substitute for durable storage. This app currently creates no user-facing report/document files. APS Files is for object/file storage; it does not supply the transactional database semantics required by Verigate's accounting/nonce ledger. No APS-based replacement for SQLite/key persistence is implemented.
- [ ] Verify the real Cloud Agent invokes the Executa from the owning App context and completes App-write → Executa-read → ETag-delete. Current Anna docs describe protocol v2 + installed/enabled state + host-attested App context as the gate; do not assume a separate storage-permission toggle.

### Explicit data-directory safety — local implementation and tests

- `VERIGATE_ANNA_DATA_DIR` is authoritative when explicitly set. If that exact directory cannot be created or written, Executa fails closed instead of silently falling back.
- When no explicit override exists, `ANNA_WORKSPACE_DIR/verigate-authority` is selected when Anna injects the platform workspace. Only without either authoritative variable are local fallbacks evaluated.
- This prevents a configured Cloud path from silently moving issuer identity and accounting history to an ephemeral install/home/temp location.
- `tests/test_anna_data_directory.py` covers explicit-path success/failure, Anna workspace selection, workspace failure without fallback and local default resolution. `tests/test_evidence_snapshot_migration.py` covers the SQLite migration described below.
- These tests prove resolver behaviour on the laptop, not that Anna Cloud actually injects and preserves the expected mounted workspace during its full lifecycle.

### Persistence architecture decision — no unsafe SQLite snapshot shortcut

The APS guide distinguishes KV (small JSON state) from Files (durable objects). It does not provide a transactional database API or conditional atomic replacement of a multi-table SQLite database. A naive pattern of downloading a SQLite file, mutating it locally, uploading it, and updating a KV pointer with ETag is not sufficient: concurrent Executa invocations can start from the same generation, and a CAS conflict after a local authorization/accounting transaction does not automatically roll back or merge that transaction. WAL sidecars and crash consistency add another failure mode.

Therefore:
- Do not mirror the live SQLite file to APS Files after each tool call and call that durable accounting.
- Do not put the SQLite database or issuer private key into the App's shared scope merely to make a persistence test pass.
- APS KV may hold small private metadata; APS Files may hold immutable snapshots or exports, but neither is currently an adequate replacement for the atomic transaction semantics used by `core.storage.Storage`.
- The safe production path is a durable transactional database with per-user/tool isolation and atomic nonce/accounting operations, or an Anna-supported persistent transactional volume with documented single-writer guarantees. APS KV/object storage alone is not a substitute for those transaction semantics. The adapter must commit the database transaction before returning a signed authorization, and must preserve replay records and issuer-key identity across restarts.

Infrastructure check on 2026-11-06: the connected Render workspace has one free web service (`verigate-portaldot-explorer`) and no Postgres instances. No database or paid resource was created. Do not provision paid infrastructure without the user's explicit approval.

### Persistence durability — BLOCKED pending real Cloud Agent restart test

The policy/accounting database (`verigate.db`) and Ed25519 issuer keypair (`issuer.key` / `issuer.pub`) are stored beneath `VERIGATE_ANNA_DATA_DIR` when explicitly configured, otherwise beneath `ANNA_WORKSPACE_DIR/verigate-authority` when the Anna platform provides its workspace. Local fallback directories are used only when neither authoritative variable is present. Anna documents `/data/workspace` as the Cloud Agent durable workspace volume; it survives process restart, suspend/wake and image upgrades, but a fully dormant Cloud Agent and its volume may be reclaimed after about three days. APS remains the platform-side authoritative store decoupled from the Agent lifecycle. The local tests do not prove the actual Cloud mount, host lifecycle or APS durability.

The local binary smoke test uses a temporary data directory and verifies one running process, including a mock Sampling round-trip; it does not prove that the keypair and SQLite state survive a real Cloud Agent process restart, tool reinstall, image upgrade, or three-day dormancy reclamation. Durable state beyond that lifecycle must be checkpointed to APS using a design that preserves transaction and replay guarantees.

Before calling the App Cloud-ready:
1. In a real Cloud Agent, record the issuer public-key fingerprint and a persisted audit/history or spend-state record.
2. Restart the Agent / Executa process without deleting its data.
3. Confirm the issuer fingerprint is unchanged and the persisted policy/accounting record remains.
4. Repeat after an Executa package update/reinstall if the platform supports that lifecycle.
5. If state does not survive the supported lifecycle, stop authorization issuance until a documented Anna-supported durable-storage design exists: a transactionally persistent DB/volume for policy/accounting and an appropriately protected durable key store for the issuer key. Do not assume APS Files/KV by itself is a drop-in SQLite database. Do not silently generate a new issuer key or reset spend history after a restart.

Do not mark this gate passed based on local smoke tests or mocked APS responses.

## Release decision

A candidate is **source-ready** only when sections 1–4 are green. It is **Anna-ready** only after sections 5–6 pass, including the real Cloud Agent persistence test. Marketplace submission/review/public release is a separate action and must not be performed as part of these checks.