# Verigate Authority — Anna release gate

This gate prevents incremental Marketplace uploads. A candidate is not ready merely because the Python unit suite or the UI mock passes.

## 1. Source and protocol consistency

- [ ] `app.json` bundled handle resolves to the actual Executa directory.
- [ ] Root App manifest requests that bundled handle and grants the UI invocation permission.
- [ ] Every method invoked by `bundle/app.js` exists in the Executa `describe` manifest.
- [ ] Every method's parameter names, types and required flags match its implementation.
- [ ] Executa identity and version agree across `executa.json`, the Python plugin and its `describe` response.
- [ ] The active distribution profile is the intended release profile and includes `linux-x86_64` for Anna Cloud Agent.
- [ ] Archive entrypoints and archive-root manifests match the actual built artifacts.

## 2. Deterministic authority and cryptography

- [ ] ALLOW, WARN and BLOCK are produced by the deterministic policy engine, never by Anna's LLM.
- [ ] AI risk flags can escalate ALLOW to WARN but cannot downgrade WARN or BLOCK.
- [ ] Missing or ambiguous fields stop before policy invocation.
- [ ] Every Decision Receipt is verified before any decision is displayed, including fresh decisions returned during execution authorization.
- [ ] Every Execution Authorization is signature-verified, unexpired, and bound to the exact agent, action, target, amount, asset, network and resource shown in the UI.
- [ ] Missing keys, malformed responses, invalid signatures and unexpected response envelopes fail closed without displaying a decision or permission.

## 3. Execution boundary

- [ ] A preview check is non-persistent and never submits a transaction.
- [ ] Execution Authorization is issued only after a separate explicit user confirmation and a fresh persistent policy check returns ALLOW.
- [ ] Verify that the Agent cannot invoke authorization/consumption tools directly from chat to bypass the UI confirmation. If the runtime exposes those methods to the model, require a server-verifiable UI-origin confirmation; a prompt instruction and client-supplied boolean alone are not a security boundary.
- [ ] WARN and BLOCK never receive execution authority.
- [ ] The wallet path is limited to the explicitly supported native-USDC networks.
- [ ] The exact signed transaction is reconstructed and compared before wallet submission.
- [ ] ExecutionRouter consumes the one-time authorization before the wallet is asked to sign.
- [ ] Replay of a consumed authorization is rejected.
- [ ] Wallet rejection, account changes, chain changes and post-consumption failures are reported without suggesting that funds were sent.

## 4. Automated release checks

Required before a candidate can be called source-ready:

- [ ] Full Python unit and integration suite.
- [ ] Contract and ExecutionRouter end-to-end suites.
- [ ] Anna UI end-to-end tests against the real bundle and real Python Executa process, with scripted LLM responses.
- [ ] Cross-layer App/Executa/manifest contract tests.
- [ ] Multi-platform binary builds and smoke tests for every declared platform.
- [ ] `anna-app validate --strict` on the exact release candidate.
- [ ] The final CI run is green on the exact candidate commit (not merely an earlier parent commit).

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
