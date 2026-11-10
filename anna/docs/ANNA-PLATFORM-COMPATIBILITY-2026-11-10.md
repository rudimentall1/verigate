# Anna platform compatibility review — 10 November 2026

**Scope:** Verigate Authority Anna App and its bundled Python Executa only.  
**Purpose:** Apply current Anna platform guidance without importing outdated manifest rules or unnecessary platform features.

## Decision summary

| Area | Decision | Reason |
|---|---|---|
| App UI → Runtime → Executa → reverse Sampling → Anna LLM | Keep | This is the documented single-request integration pattern and is already implemented. |
| Anna Agent Session | Do not add | Verigate handles one payment request per user action. Agent Session is for ongoing multi-turn work, streaming, cancellation and recovery. It would add lifecycle state without solving a current product requirement. |
| App-scope APS KV | Keep | Short-lived, small JSON approvals belong in KV. The App creates a random nonce with a 60-second TTL; Executa reads and conditionally deletes it using the returned ETag. |
| APS Files / Host Upload | Do not add | The App does not currently persist large user files or transfer payloads near the invoke size limit. A file subsystem would be unused infrastructure. |
| App manifest schema 4 | Keep current shape | The 6 November platform update removed legacy method-level ACL declarations. Do not reintroduce old `ui.host_api.storage`, `permissions`, or App-level `host_capabilities` from older tutorials. |
| Binary and tool-protocol checks | Strengthen | Strict schema validation is necessary but does not prove the final archive starts, describes, invokes and survives errors on the target Agent. |

## 1. App and Executa invocation architecture

The App uses the documented single-turn flow:

`Anna App UI → Anna Runtime → bundled Verigate Executa → reverse Sampling → Anna host LLM`

Anna 101 explicitly presents this pattern for an App that sends a user request to a bundled Python tool, which then calls the host LLM through reverse Sampling. The model interprets the request; deterministic Verigate policy remains the authority for ALLOW/WARN/BLOCK.

Do not move payment authorization into an autonomous Agent Session. Agent Session is intended for ongoing conversations that need shared multi-turn context, per-turn tool scope, streaming, cancellation and session recovery. Verigate's payment workflow is deliberately transactional: each request is interpreted, checked, explicitly approved, and then handed to a one-time execution path. A long-lived natural-language session is not needed to authorize a payment and must not become a substitute for the signed authorization state.

## 2. Schema 4 and capability declarations

The 6 November 2026 Anna 1.1.0-beta.211–beta.220 changelog supersedes older examples that describe the previous permission gates.

For schema 4:
- The old first-launch capability grant/editor is removed.
- App-level `permissions`, `host_capabilities`, and per-method `ui.host_api` namespaces such as `storage`, `tools`, and `llm` are legacy declarations and must not be copied into a current schema-4 App manifest.
- The App's own `app` storage scope is self-owned. Declarations in `storage.scopes` are for non-self scopes such as cross-App `user` data.
- An installed, enabled App receives platform host service access under the current runtime model. The remaining declarations are the ones with another party or scope boundary, not a method-by-method ACL.

**Important distinction:** the App root manifest and the Executa's own JSON-RPC `describe` manifest are different contracts. Do not copy or remove a field from one merely because a similarly named field appears in the other. The Executa's runtime `MANIFEST`, its published description file, and the actual `describe` response must remain byte-for-byte equivalent as structured data; this is checked by `test_published_protocol_manifest_matches_runtime_describe`.

Verigate's current root App manifest is schema 4, declares the bundled Executa dependency, and does not add the retired per-method host API ACLs.

## 3. APS: use KV, not Files, for one-time approvals

The approval records are small JSON state, not user documents or binary outputs. App-scope KV is the correct primitive.

Current lifecycle:
1. App generates a cryptographically random 24-byte nonce.
2. App writes a small approval record to its private `app` scope with a 60-second TTL.
3. Executa reads the record, validates its kind and exact payment/transaction fields, checks the time window, and deletes it with the ETag returned by APS.
4. A missing record, expired record, mismatched field, or failed ETag precondition fails closed.

Keep `exists` distinct from the stored value; null, false, zero and empty strings can all be legitimate values in KV. ETags are opaque compare-and-swap tokens. Do not replace them with a locally calculated hash.

Do not add APS Files for transient approval tokens. Use APS Files only if the product introduces persistent user-managed files such as reports or exported artifacts. Use Host Upload only for temporary transfer/preview or content too large for invoke. The current wallet authorization payload is small and must stay small.

The October 20 APS tutorial describes older CLI 0.1.59 permission declarations. Its KV, ETag, pagination, upload-finalization and size-limit concepts remain useful, but its old App `ui.host_api.storage` and grant instructions are superseded for schema 4 by the November 6 changelog.

## 4. Anna invoke failure semantics

The November 6 platform update changes `tools.invoke` failure timing:
- A command that receives no Agent acknowledgement can return `executa_unavailable` with `reason: no_ack` after roughly five seconds rather than waiting for the old 90-second timeout.
- The platform watches for a late result for 30 seconds. A late result is evidence that the command did execute, even though the original caller received `no_ack`.
- Therefore `no_ack` is not proof that a side effect did not occur. Side-effecting operations must be idempotent or queried before retry.
- Preserve `invoke_id`, `client_id`, `command_id`, and `reason` in diagnostics.

Verigate must not retry a consumed execution authorization after an ambiguous invoke result. The App may record `ABORTED` only when the Executa's durable nonce ledger proves that ExecutionRouter consumed the exact authorization and the wallet request was never started. If consumption cannot be proven, no negative receipt is issued and the UI disables retry for that authorization. If `eth_sendTransaction` started, only EIP-1193 error `4001` is explicit user rejection; other ambiguous outcomes are `UNKNOWN`.

Wallet outcome receipts are Ed25519-signed by the Anna installation issuer. They are Anna self-reports, not wallet signatures or independent on-chain evidence:
- `REJECTED`: EIP-1193 `4001` during `eth_sendTransaction`.
- `ABORTED`: proven pre-wallet abort or a lost Router response with an existing consumed nonce record.
- `UNKNOWN`: the wallet request started, but the result is ambiguous and no valid transaction hash was returned.
- `SUBMITTED`: the wallet returned a transaction hash and Anna recorded it. This remains executor self-report, not chain confirmation.

Only `SUBMITTED` receipts are eligible for network polling. `ExecutionMonitor` returns `REJECTED`, `ABORTED` and `UNKNOWN` as terminal local outcomes without querying an RPC provider; `ExecutionRouter.confirm_execution_receipt` does not transition them. Regression coverage asserts that these statuses never trigger chain polling.

## 5. Pre-release inspection gates

Use the official [Anna App Backend Tool Executa Pre-Release Inspection Guide](https://forum.anna.partners/t/anna-app-backend-tool-executa-pre-release-inspection-guide/380) as the release checklist. Its status vocabulary is mandatory:
- `PASS`: actually executed and supported by evidence.
- `FAIL`: observed non-compliance.
- `WARN`: compatibility or non-blocking discrepancy, explained.
- `BLOCKED`: a target, authorization, environment or artifact is unavailable.
- `N/A`: genuinely not applicable, with a reason.

For each release candidate, check:
1. Actual project root, CLI/runtime versions, branch, commit, and dirty state.
2. `app.json` bundled reference → actual Executa directory → `executa.json`.
3. Root App `required_executas` and `ui.bundle.entry` against the actual bundle.
4. Executa manifest, code-built runtime `MANIFEST`, method dispatch, parameters, and frontend `method`/argument shapes.
5. JSON-RPC `initialize`, repeated `describe` calls with distinct IDs, single-line UTF-8 framing, stdout purity, continued stdin processing, error recovery and clean EOF.
6. Each final binary archive: extract it, verify archive-root manifest and entrypoint, launch the extracted executable, repeat `describe` and at least one safe `invoke`.
7. Frontend success, business failure, RPC error, timeout, missing-tool, and ambiguous-consumption UI behavior.
8. Actual Cloud Agent install/invocation and App-context APS behavior. Do not replace this with local tests or CLI validation.

Strict schema validation, source tests, and a source-launched plugin are not substitutes for testing the final archive. Unknown or untested target platforms must be marked `BLOCKED`, not passed.

## 6. Current implementation and evidence

Current working release candidate:
- Anna App source: **0.1.30** (not uploaded or cut as an immutable Anna version).
- Bundled Executa source: **0.1.17**.
- Root App manifest requires bundled Executa >= **0.1.17**.
- Current immutable Anna Console Draft remains App **0.1.29** / Executa **0.1.16**. This work has not replaced or published it.

At commit `29847d003618a47ad0bef2eb4259673a14c8cba4`, GitHub Actions run [42873145755](https://github.com/rudimentall1/verigate/actions/runs/42873145755) passed:
- 612 Python tests;
- Anna UI E2E 64/64;
- Contracts;
- strict schema-4 validation;
- Linux Executa 0.1.17 build and extracted-binary smoke test, including `describe`, ALLOW decision, one-time App approval consumption, wallet-handoff consumption, and signed SUBMITTED receipt verification.

Subsequent commits preserve invoke correlation fields in wallet outcome diagnostics and add a `no_ack` regression assertion. Their CI must pass before merge.

Still separate release gates:
- Current PR source has not been uploaded as App 0.1.30 / Executa 0.1.17 to Anna Console.
- A fresh Cloud Agent installation and live invoke of the new Executa 0.1.17 remain unverified.
- The 0.1.17 cross-platform archives for Windows/macOS must be built and inspected before claiming those targets pass.
- No live payment was broadcast by these source/CI tests. The 9 November real Brave + MetaMask recording remains the separate proof of live wallet hand-off ending in explicit user signature rejection; it is not a successful payment.

## Official source material

- [Build on Anna 101](https://forum.anna.partners/t/build-on-anna-101/228) — App → Executa → reverse Sampling flow and local project lifecycle.
- [Build on Anna 102 — Tool & Executa](https://forum.anna.partners/t/build-on-anna-102-tool-executa/381) — configuration, describe, tool methods and packaging.
- [Build on Anna 103 — Agent Session Usage](https://forum.anna.partners/t/build-on-anna-103-agent-session-usage/399) — Session lifecycle, use cases, cancellation and recovery.
- [Getting Started with Anna APS](https://forum.anna.partners/t/getting-started-with-anna-aps-save-files-find-them-again-and-know-when-to-use-upload/437) — KV, Files, scope, ETag, Upload and invoke size limits (CLI baseline stated by that post: 0.1.59).
- [Anna App Backend Tool Executa Pre-Release Inspection Guide](https://forum.anna.partners/t/anna-app-backend-tool-executa-pre-release-inspection-guide/380) — release inspection status, evidence and artifact checklist.
- [Anna 1.1.0 beta.211–beta.220 / CLI 0.1.64 changelog, 6 November 2026](https://forum.anna.partners/t/anna-1-1-0-beta-211-beta-220-anna-ai-cli-0-1-64-permission-gates-are-gone-manifest-schema-4-shared-node-22-chrome-runtime-for-executas-async-invoke-reliability-overhaul-faster-app-opens-harness-tools-fixed/542) — current schema-4, permission, runtime and `no_ack` behavior.
