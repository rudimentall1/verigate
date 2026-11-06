# Verigate Authority — Anna release gate

## Candidate checkpoint — 2026-11-06

- Candidate: Anna App **0.1.13**, bundled Executa **0.1.12**.
- Branch: `integrate/anna-0.1.9-mainline`; PR #16 remains open. No merge to `main`.
- Verified source head: `6b237609bc82f7993b2e68e84d5fc2be490f1587`.
- GitHub Actions run **#549** is green on that exact head:
  - 509 Python tests passed.
  - Contract and ExecutionRouter suites passed.
  - Official `@anna-ai/cli@0.1.59 validate --strict` passed.
  - Anna UI end-to-end: **28/28 passed**, including in-App dialog cancellation, duplicate-click protection and direct-call denial with and without App context.
  - Linux PyInstaller binary built and smoke-tested; the smoke test covered App-scope approval, wallet hand-off and replay rejection.
  - Linux `0.1.12` archive verified; archive root contains `manifest.json` and `verigate-authority`.
- Four-platform release is still pending: Windows and both macOS targets have not yet been built.
- Nothing has been uploaded to Anna Dashboard. No Marketplace publish/review and no wallet transaction have occurred.

Next: run the existing multi-platform `workflow_dispatch` on this branch with version `0.1.12`; then perform one consolidated real Anna acceptance pass. Do not merge or publish to the Marketplace as part of this gate.

This gate prevents incremental Marketplace uploads. A candidate is not ready merely because the Python unit suite or the UI mock passes.

## 1. Source and protocol consistency

- [x] `app.json` bundled handle resolves to the actual Executa directory.
- [x] Root App manifest requests that bundled handle and grants the UI invocation permission.
- [x] Every method invoked by `bundle/app.js` exists in the Executa `describe` manifest.
- [x] Every method's parameter names, types and required flags match its implementation.
- [x] Executa identity and version agree across `executa.json`, the Python plugin and its `describe` response.
- [x] The active distribution profile is the intended release profile and includes `linux-x86_64` for Anna Cloud Agent.
- [ ] Archive entrypoints and archive-root manifests match the actual built artifacts.

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
- [ ] Multi-platform binary builds and smoke tests for every declared platform.
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

## Release decision

A candidate is **source-ready** only when sections 1–4 are green. It is **Anna-ready** only after section 5 passes. Marketplace submission/review/public release is a separate action and must not be performed as part of these checks.
