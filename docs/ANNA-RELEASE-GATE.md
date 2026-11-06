# Verigate Authority — Anna release gate

## Candidate checkpoint — 2026-11-06

- Candidate: Anna App **0.1.13**, bundled Executa **0.1.12**.
- Branch: `integrate/anna-0.1.9-mainline`; PR #16 remains open. No merge to `main`.
- Current PR head: `a325e74a8f79b3bf8e1882196f7b2a2755d3f3d8`; PR #16 remains open and unmerged. This latest commit updates release-gate documentation only.
- Latest code CI run **#589** passed on code head `65109b45a5b654b1ad2cfb53d2b32166fc71de4a`: 509 Python tests, contract/ExecutionRouter tests, Anna UI E2E, and official Anna CLI strict manifest/Host API validation.
- Multi-platform binary workflow run **#17** (run ID `42186375291`, binary source commit `cd768515c1b178333a0d4bfbefd8f2154e988951`) completed successfully on all four targets: Linux x86_64, Windows x86_64, macOS ARM64 and macOS Intel x86_64. Each target packaged the binary, verified the SHA-256 sidecar and archive manifest/entrypoint, extracted the binary from the final archive, ran the protocol/security smoke suite, and uploaded the archive plus checksum.
- I downloaded all four run #17 artifacts and independently verified the outer Actions artifact digests, archive-sidecar SHA-256, archive-root manifest, platform entrypoint, and Unix executable bit. The resulting package SHA-256 values are:
  - Linux x86_64: `c8bd06566bd22b76f06b2e6fb1e35c780b661b69906b85b09ba245c649abed0d`
  - Windows x86_64: `39c5a268d9c2773917df78bdce191dec55cb3ea058302ce7117353aab742371d`
  - macOS ARM64: `b6ace24d9be7607ddbd2952fc7dfd26fe1ffefa512faca34746d7e6a24b5a0cc`
  - macOS Intel x86_64: `fc6cf585bc816243327a67f408d53cbe3ff928cb5ab61cce956634f9e136fdbc`
- The release job completed successfully and created a **draft** GitHub Release with the four archives and four checksum sidecars. Draft URL reported by GitHub CLI: https://github.com/rudimentall1/verigate/releases/tag/untagged-8d1c909e607f189c17ed. GitHub's draft-release flow uses an untagged URL until the draft is published; this is not the public version/tag. The draft has not been published.
- A ready-to-copy package bundle has been assembled outside the repository, with all eight files under `anna/executas/verigate-authority/dist/`: `anna-executa-dist-0.1.12.zip` (SHA-256 `f3b573a0835f85705bebee9dec16797500b659307f72f893b36f4e039e67e318`).
- `app.json`, `manifest.json`, `bundle/index.html`, `bundle/app.js`, and `executa.json` follow Anna's Bundled Executa guidance: stable handle `verigate-authority`, `bundled:verigate-authority`, `required:bundled:verigate-authority`, generated `window.__ANNA_TOOL_IDS__` mapping with local dev fallback, and the local development tool_id in `executa.json`.
- No Anna candidate version has been uploaded. No Marketplace review/public release or wallet transaction has occurred.

Next: put the verified `dist/` bundle into the local project checkout, then run the Anna CLI publish step once to create an immutable candidate version (not a Marketplace submission). Install that candidate and perform one consolidated local + real Anna Cloud Agent acceptance. The key/database persistence gate below remains blocking until the Cloud restart test is passed. Do not publish the draft GitHub Release, submit for Marketplace review, or merge PR #16 as part of this gate.

Reference: [Anna Forum — Build on Anna 101](https://forum.anna.partners/t/build-on-anna-101/228).

This gate prevents incremental Marketplace uploads. A candidate is not ready merely because the Python unit suite or the UI mock passes.

## 1. Source and protocol consistency

- [x] `app.json` bundled handle resolves to the actual Executa directory.
- [x] Root App manifest requests that bundled handle and grants the UI invocation permission.
- [x] Every method invoked by `bundle/app.js` exists in the Executa `describe` manifest.
- [x] Every method's parameter names, types and required flags match its implementation.
- [x] Executa identity and version agree across `executa.json`, the Python plugin and its `describe` response.
- [x] The active distribution profile is the intended release profile and includes `linux-x86_64` for Anna Cloud Agent.
- [x] Archive entrypoints, archive-root manifests, checksums and executable permissions match the actual built artifacts; each extracted package binary passed the smoke suite.

## 2. Deterministic authority and cryptography

- [x] ALLOW, WARN and BLOCK are produced by the deterministic policy engine, never by Anna's LLM.
- [x] AI risk flags can escalate ALLOW to WARN but cannot downgrade WARN or BLOCK.
- [x] Missing or ambiguous fields stop before policy invocation.
- [x] Every Decision Receipt is verified before any decision is displayed, including fresh decisions returned during execution authorization.
- [x] Every Execution Authorization is signature-verified, unexpired, and bound to the exact agent, action, target, amount, asset, network and resource shown in the UI.
- [x] Missing keys, malformed responses, invalid signatures and unexpected response envelopes fail closed without displaying a decision or permission.
- [x] Issuer private keys are stored with POSIX mode 0600 inside a mode-0700 app data directory; legacy permissions are tightened and symlinked key paths are rejected.

## 3. Execution boundary

- [x] A preview check is non-persistent and never submits a transaction.
- [x] Execution Authorization is issued only after a separate explicit user confirmation and a fresh persistent policy check returns ALLOW.
- [x] Direct model/tool invocation without a UI-created approval record is rejected both outside App context and when App context exists; no client-supplied boolean can mint approval.
- [x] Both privileged methods require separate 60-second App-scope approvals: one bound to the exact payment before issuing Execution Authorization, and one bound to the exact authorization ID and transaction before ExecutionRouter consumption. Each record is ETag-deleted exactly once.
- [x] Critical approvals use the in-App dialog rather than browser `window.confirm()`; dialog cancellation writes no approval record and does not consume an existing permission.
- [x] WARN and BLOCK never receive execution authority.
- [x] The wallet path is limited to the explicitly supported native-USDC networks.
- [x] The exact signed transaction is reconstructed and compared before wallet submission.
- [x] ExecutionRouter consumes the one-time authorization before the wallet is asked to sign.
- [x] Replay of a consumed authorization is rejected.
- [x] Wallet rejection, account changes, chain changes and post-consumption failures are reported without suggesting that funds were sent.

## 4. Automated release checks

Required before a candidate can be called source-ready:

- [x] Full Python unit and integration suite.
- [x] Contract and ExecutionRouter end-to-end suites.
- [x] Anna UI end-to-end tests against the real bundle and real Python Executa process, with scripted LLM responses.
- [x] Cross-layer App/Executa/manifest contract tests.
- [x] Multi-platform binary builds, archive verification and extracted-package smoke tests for all four declared platforms.
- [x] `anna-app validate --strict` on the exact release candidate.
- [x] The final CI run is green on the exact candidate commit (not merely an earlier parent commit).

## 5. Real Anna acceptance — one consolidated pass

Only after sections 1–4 pass, install one candidate in a test Agent and run this matrix. Do not publish successive fixes one by one.

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
| Tool unavailable / bad envelope / missing issuer key | Clear fail-closed error; no decision inferred |

The real Anna acceptance pass must record the exact App version, Executa version, Agent type (Cloud or local), tool handle resolution, test results and relevant error text. Never infer cloud compatibility from local jsdom tests.

## 6. Additional Anna platform guidance — 2026-11-06

Reviewed the official forum guides:
- Build on Anna 102 — Tool & Executa.
- Build on Anna 103 — Agent Session Usage.
- Getting Started with Anna APS — Save Files, Find Them Again, and Know When to Use Upload.

### Executa protocol — source review passed; Cloud remains unverified

- [x] App bundle uses the CLI-generated `window.__ANNA_TOOL_IDS__` mapping with a development fallback.
- [x] `describe` returns the tool manifest directly in JSON-RPC `result`; no extra `manifest` or business-result wrapper.
- [x] Tool parameter declarations use the required list-of-objects format and supported types.
- [x] `initialize` negotiates protocol v2 and advertises KV support.
- [x] The process keeps reading stdin after `describe`, correlates APS reverse-RPC responses, and returns one JSON-RPC response per line.
- [x] Linux, Windows, macOS ARM64 and macOS Intel binaries passed the current smoke-test workflow.
- [ ] Actual install, tool discovery and repeated invocation on a real Anna Cloud Agent remain unverified.

### Agent Session — deliberately not required for this release

The current payment intake uses one bounded `llm.complete` call per explicit check. Missing or ambiguous details are shown as form questions; the user edits the form and starts a fresh check. It does not promise a persistent chat conversation, so the stateless completion API is sufficient for this interaction model.

- [x] No automatic Agent Session or Agent tool-routing permission is enabled.
- [ ] A future conversational intake upgrade may adopt Agent Session for follow-up context, streaming, cancellation and refresh recovery.
- [ ] If adopted, create one Session per conversation, restore it by saved session UUID, and use `quotaCaps.allowed_tools: []` for the intake model. The LLM must never receive a path to privileged Verigate authorization or wallet-consumption methods; only explicit App UI buttons may invoke those methods.

### APS — approval KV path passed by code review; actual Host grant/persistence pending

- [x] App UI writes only a short-lived unique approval record in the private `app` KV scope.
- [x] The bundled Executa reads the approval, validates its nonce, exact action binding and 60-second expiry, then consumes it with ETag-conditional delete.
- [x] App manifest permits the UI's `storage.set`; Executa declares `aps.scope.app.read` and `aps.scope.app.write` and negotiates KV in `initialize`.
- [x] Host Upload is not used as a substitute for durable storage. This app currently creates no user-facing report/document files; APS Files is the appropriate Anna API to evaluate for durable Executa state. That separate database/key persistence integration has not yet been implemented and remains blocked below.
- [ ] Verify the user's real APS storage grant and the full App-write → Executa-read → ETag-delete flow on Anna Cloud Agent.

### Explicit data-directory safety — implemented, CI pending

- `VERIGATE_ANNA_DATA_DIR` is now authoritative when set. If that exact directory cannot be created or written, Executa fails closed instead of silently falling back to the install directory, home directory, or system temp.
- This prevents a misconfigured persistent path from appearing healthy while silently creating a new issuer key and empty accounting database elsewhere.
- Added `tests/test_anna_data_directory.py` for explicit-path success, explicit-path failure without fallback, and legacy resolution when no override is set.
- This is a safety guard, not proof that Anna Cloud's selected directory is persistent. Cloud restart/reinstall verification remains mandatory.

### Persistence architecture decision — no unsafe SQLite snapshot shortcut

The APS guide distinguishes KV (small JSON state) from Files (durable objects). It does not provide a transactional database API or conditional atomic replacement of a multi-table SQLite database. A naive pattern of downloading a SQLite file, mutating it locally, uploading it, and updating a KV pointer with ETag is not sufficient: concurrent Executa invocations can start from the same generation, and a CAS conflict after a local authorization/accounting transaction does not automatically roll back or merge that transaction. WAL sidecars and crash consistency add another failure mode.

Therefore:
- Do not mirror the live SQLite file to APS Files after each tool call and call that durable accounting.
- Do not put the SQLite database or issuer private key into the App's shared scope merely to make a persistence test pass.
- APS KV may hold small private metadata; APS Files may hold immutable snapshots or exports, but neither is currently an adequate replacement for the atomic transaction semantics used by `core.storage.Storage`.
- The safe production path is a durable transactional database with per-user/tool isolation and atomic nonce/accounting operations, or an Anna-supported persistent transactional volume with documented single-writer guarantees. The adapter must commit the database transaction before returning a signed authorization, and must preserve replay records and issuer-key identity across restarts.

Infrastructure check on 2026-11-06: the connected Render workspace has one free web service (`verigate-portaldot-explorer`) and no Postgres instances. No database or paid resource was created. Do not provision paid infrastructure without the user's explicit approval.

### Persistence durability — BLOCKED pending real Cloud Agent restart test

The policy/accounting database (`verigate.db`) and Ed25519 issuer keypair (`issuer.key` / `issuer.pub`) are currently kept in a local data directory. The resolver tries the directory beside the Executa binary, then `~/.verigate-authority`, then the system temporary directory. They are not currently stored through APS.

The binary smoke test uses a temporary data directory and verifies a single running process; it does not prove that the keypair and SQLite state survive a Cloud Agent process restart, tool reinstall, or replacement of the binary package.

Before calling the App Cloud-ready:
1. In a real Cloud Agent, record the issuer public-key fingerprint and a persisted audit/history or spend-state record.
2. Restart the Agent / Executa process without deleting its data.
3. Confirm the issuer fingerprint is unchanged and the persisted policy/accounting record remains.
4. Repeat after an Executa package update/reinstall if the platform supports that lifecycle.
5. If state does not survive the supported lifecycle, implement durable storage for the private signing key and policy database using the appropriate private APS scope or another Anna-supported persistent store. Do not silently generate a new issuer key or reset spend history after a restart.

Do not mark this gate passed based on local smoke tests or mocked APS responses.

## Release decision

A candidate is **source-ready** only when sections 1–4 are green. It is **Anna-ready** only after sections 5–6 pass, including the real Cloud Agent persistence test. Marketplace submission/review/public release is a separate action and must not be performed as part of these checks.
