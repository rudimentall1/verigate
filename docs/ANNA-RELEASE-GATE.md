# Verigate Authority — Anna release gate

## Verified checkpoint — 2026-11-07

This checkpoint replaces the stale 2026-11-06 candidate header. It records source, CI, local CLI and authenticated Anna lifecycle state. A green source build is not the same as a successful Anna Cloud Agent install, Marketplace approval, or publication.

### Source and local checkout

- Repository: [rudimentall1/verigate](https://github.com/rudimentall1/verigate).
- Working branch: `integrate/anna-0.1.9-mainline`.
- Verified HEAD: `d79d660e08314a4e75aba23319967047f7e80dcb` (signed merge commit, 2026-11-07 12:54:10 UTC+5).
- PR [#22](https://github.com/rudimentall1/verigate/pull/22) is merged. It adds policy-only preview after an actual Host LLM invocation failure, uses only explicit form values, discloses that contextual AI review did not run, keeps execution permission disabled, and rejects malformed LLM response data rather than treating it as an outage.
- The Windows checkout at `C:\Users\User\Desktop\Work\verigate-anna-0.1.13` was initially detached at `addef3a`. Its worktree was clean; it was switched to `integrate/anna-0.1.9-mainline` and fast-forwarded to the verified merge commit. Final status was clean and matched `origin/integrate/anna-0.1.9-mainline`.
- Local toolchain: Node.js `v22.23.4`, `@anna-ai/cli` `0.1.59`, app-schema dispatcher `0.27.0`.
- `anna-app validate --strict` passed on this checkout (exit code 0).
- No source-code changes were made during this checkpoint update.

### CI and Executa artifacts

- CI run [42353190020](https://github.com/rudimentall1/verigate/actions/runs/42353190020) passed on the exact merge commit. Jobs: `anna-ui`, `test`, and `contracts`.
- Binary workflow [42353190033](https://github.com/rudimentall1/verigate/actions/runs/42353190033) passed on the exact merge commit. Linux x86_64, Windows x86_64, macOS ARM64 and macOS Intel x86_64 all built, packaged, extracted and smoke-tested successfully. The workflow's draft-release job also completed successfully.
- The GitHub Executa release is a **draft**, not a public app release. The current release listing showed `anna-verigate-authority-v0.1.13` as draft and `0.1.12` as the published Executa release. Do not equate either state with Anna Marketplace publication.
- Local Executa source/manifest version is `0.1.13`. The production identity is cached in `anna/.anna/executas.lock.json` as `tool-rinat-verigate-authority-2um8gwhw`; the Executa identity cache records ID `1164`. The local `tool-dev-verigate-authority` value is only the development fallback.
- The four `0.1.13` platform archives and checksum sidecars are present under `anna/executas/verigate-authority/dist/`.

### Authenticated Anna Developer state

Read through the locally authenticated `anna-app` CLI (host `https://anna.partners`):

- App: `Verigate Authority`, slug `verigate-authority`, ID `382`.
- App status: `PENDING_REVIEW`.
- Latest immutable App version: `0.1.17`, ID `1981`; this exact version is pinned as the current review candidate.
- CLI reports 16 immutable versions. The versions listing reports `published=—` for all listed versions; no Marketplace-published version was shown.
- The checked-out `anna/app.json` still says `0.1.15`. It is behind the server's latest cut (`0.1.17`).
- App `0.1.17` predates merge commit `d79d660e` and therefore does **not** contain the PR #22 UI fallback changes. Do not describe the in-review version as containing those changes.
- `anna-app apps push --dry-run --skip-executa-publish` completed without mutation and reported a prospective working-bundle content hash beginning `5db07bb44e6d`.
- `anna-app apps cut 0.1.18 --dry-run` completed without mutation and reported that it would upload the declared Executa binary artifacts and cut App version `0.1.18`. No push, cut, review submission, or release was performed by this checkpoint.
- CLI help confirms: `apps publish` is the composite `push + cut`; it does **not** publish to the Marketplace. `apps submit-review` pins a review candidate; `apps release <version>` is the later go-live operation after approval. A new cut during an active review does not replace the pinned review candidate until review is explicitly re-submitted.
- The CLI's `apps grants` command returned “no grants endpoint data available”; this is not evidence of a grant or of MAU performance.

### Outstanding Anna runtime and durability gates

- A real Anna Cloud Agent install, Executa discovery and repeated invocation have not been demonstrated.
- The real browser/session refresh failure `POST /api/v1/auth/refresh → 401` has not been proven fixed. PR #22 tests safe fallback behavior in scripted runtime; it does not prove that a genuinely expired Anna session still permits Host tool invocation.
- The plugin negotiates Executa protocol v2 and advertises storage capability. Its one-time approval path uses App-scoped APS KV via App-context invocation and ETag-conditional deletion.
- Current Anna APS documentation says protocol v2 is the access gate: the host mints a storage token for each invocation of an installed, enabled Executa, and App scope is available only for a host-attested invocation originating from the owning App context. Legacy Executa `host_capabilities` entries such as `aps.scope.app.read/write` are ignored; they must not be represented as the actual grant mechanism. Do not assume a separate storage-permission toggle without observing the current runtime.
- APS KV/object storage is not a transactional relational database. The policy/accounting SQLite database and Ed25519 issuer keypair still resolve to a local data directory. The explicit `VERIGATE_ANNA_DATA_DIR` override now fails closed if unavailable; the data-directory tests are included in the passing full CI run. This prevents silent fallback, but does **not** prove that Anna Cloud preserves that directory across process restart, agent replacement or Executa reinstall.
- Do not mirror a live SQLite file to APS Files and call it transactional durability. Durable accounting requires a transactional persistent store or a platform-backed persistent volume with documented single-writer/atomicity guarantees; signing-key identity and replay/accounting state must survive the supported lifecycle.
- Cloud acceptance and persistence remain blocking. Do not mark this App Anna-ready based on local tests or CI.

### Program context — keep separate from PortalDot

DoraHacks hackathon **2349** is the **Anna AI App Builder Program**, not the separate PortalDot hackathon. The official Anna Founding Builder rules set the initial qualification window to 2026-09-01 through 2026-11-30. Qualification requires an approved and Marketplace-published functional App plus at least 200 Qualified App MAU in one calendar month during that window. For October/November first qualification, the standard Tier E grant at 200 MAU is $50/month; September-only launch-boost amounts no longer apply. Developer/internal QA, bots, failed/cancelled/incomplete runs and meaningless incentivized traffic do not count. See the [official Anna program rules](https://forum.anna.partners/t/turn-your-ai-agents-apps-into-recurring-monthly-grants-join-the-anna-ai-os-founding-builder-program-up-to-80k-month-pool/205).
The user's public DoraHacks submission ID/status for this program has not been independently confirmed. The separate PortalDot deadline described in the prior checkpoint was 2026-11-06 and must not be conflated with hackathon 2349.

### Next release discipline

1. Do not modify the currently pinned review candidate or submit another review until a new candidate is ready and the exact candidate version is understood.
2. Reconcile `anna/app.json` (currently `0.1.15`) with the server's next valid SemVer (`0.1.18`) before staging. The CLI dry-runs above were read-only.
3. Build/install one candidate and complete the consolidated Anna acceptance matrix below on a real test Cloud Agent, including the policy-only path, receipt verification, execution boundary, tool discovery and repeated invocation.
4. Run the restart/reinstall durability test with a recorded issuer fingerprint and persisted accounting/audit record. If state is lost, stop; do not issue execution permissions with a silently rotated key or reset history.
5. Only after the above, decide whether to switch the review candidate. Marketplace release is a separate approval/release action and is not authorized by a green CI run.

Reference: [Anna Forum — Build on Anna 101](https://forum.anna.partners/t/build-on-anna-101/228), [Anna developer docs](https://github.com/Anna-Partners/anna-developer-docs).

This gate prevents incremental Marketplace uploads. A candidate is not Anna-ready merely because the Python suite, UI mock, local strict validation or CI passes.

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

### APS — code path present; Cloud invocation/persistence unverified

- [x] App UI writes only a short-lived unique approval record in the private `app` KV scope.
- [x] The bundled Executa reads the approval, validates its nonce, exact action binding and 60-second expiry, then consumes it with ETag-conditional delete.
- [x] The Executa negotiates protocol v2 and uses App-context reverse RPC for the short-lived approval record. Legacy `host_capabilities` strings in the Executa manifest are ignored by the current Anna runtime and are not an authorization grant.
- [x] Host Upload is not used as a substitute for durable storage. This app currently creates no user-facing report/document files. APS Files is for object/file storage; it does not supply the transactional database semantics required by Verigate's accounting/nonce ledger. No APS-based replacement for SQLite/key persistence is implemented.
- [ ] Verify the real Cloud Agent invokes the Executa from the owning App context and completes App-write → Executa-read → ETag-delete. Current Anna docs describe protocol v2 + installed/enabled state + host-attested App context as the gate; do not assume a separate storage-permission toggle.

### Explicit data-directory safety — implemented, CI verified on merge commit d79d660e

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
- The safe production path is a durable transactional database with per-user/tool isolation and atomic nonce/accounting operations, or an Anna-supported persistent transactional volume with documented single-writer guarantees. APS KV/object storage alone is not a substitute for those transaction semantics. The adapter must commit the database transaction before returning a signed authorization, and must preserve replay records and issuer-key identity across restarts.

Infrastructure check on 2026-11-06: the connected Render workspace has one free web service (`verigate-portaldot-explorer`) and no Postgres instances. No database or paid resource was created. Do not provision paid infrastructure without the user's explicit approval.

### Persistence durability — BLOCKED pending real Cloud Agent restart test

The policy/accounting database (`verigate.db`) and Ed25519 issuer keypair (`issuer.key` / `issuer.pub`) are currently kept in a local data directory. When `VERIGATE_ANNA_DATA_DIR` is set, that path is authoritative and failure to use it is fatal. Only when the override is unset does the resolver fall back to the Executa-adjacent `.data` directory, `~/.verigate-authority`, then the system temporary directory. No Anna Cloud persistence guarantee has been demonstrated; the database and key are not currently stored through APS.

The binary smoke test uses a temporary data directory and verifies a single running process; it does not prove that the keypair and SQLite state survive a Cloud Agent process restart, tool reinstall, or replacement of the binary package.

Before calling the App Cloud-ready:
1. In a real Cloud Agent, record the issuer public-key fingerprint and a persisted audit/history or spend-state record.
2. Restart the Agent / Executa process without deleting its data.
3. Confirm the issuer fingerprint is unchanged and the persisted policy/accounting record remains.
4. Repeat after an Executa package update/reinstall if the platform supports that lifecycle.
5. If state does not survive the supported lifecycle, stop authorization issuance until a documented Anna-supported durable-storage design exists: a transactionally persistent DB/volume for policy/accounting and an appropriately protected durable key store for the issuer key. Do not assume APS Files/KV by itself is a drop-in SQLite database. Do not silently generate a new issuer key or reset spend history after a restart.

Do not mark this gate passed based on local smoke tests or mocked APS responses.

## Release decision

A candidate is **source-ready** only when sections 1–4 are green. It is **Anna-ready** only after sections 5–6 pass, including the real Cloud Agent persistence test. Marketplace submission/review/public release is a separate action and must not be performed as part of these checks.
