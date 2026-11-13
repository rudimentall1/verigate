# Anna App pre-release inspection — 2026-11-13

Scope: Verigate Authority App 0.1.34 / bundled Executa 0.1.20, Anna App ID 851, Executa ID 1314. This is a source and Console-state inspection. No Desktop Commander session, local Anna Cloud Agent, wallet, or paid token-consuming test was used.

## Current evidence

| Area | Status | Evidence / boundary |
|---|---|---|
| App source and manifest | PASS (source inspection) | App manifest 0.1.34; schema-4 UI bundle; bundled Executa handle declared. |
| Executa binary distribution | PASS (build/package evidence) | 0.1.20 four-platform artifacts were built in GitHub Actions run 43376084717; extracted package smoke and SHA-256 sidecars passed for macOS ARM64, macOS x86_64, Linux x86_64 and Windows x86_64. |
| Executa Console version | PASS (Console metadata) | Executa ID 1314, version ID 1086, version 0.1.20. CLI reports the four platform assets and their SHA-256 references. |
| App Console cut | PASS (Console metadata) | App ID 851, immutable version ID 2182, version 0.1.34; frozen Executa version ID 1086 / 0.1.20; UI bundle 3 files, status ready. |
| Marketplace | NOT RELEASED | App remains Draft; is_published=false; no review candidate. No release or review submission was performed. |
| Protocol manifest parity | FIX APPLIED; CI RE-RUN REQUIRED | Latest PR CI failed one of 664 tests because the UTF-8 shield icon in the checked-in Executa manifest was mojibake while runtime describe used the proper Unicode character. Fixed the checked-in manifest in commit 25d6b06f680a6d0512610d9621f3e67a1bb56530. A successful post-fix CI run has not yet been observed. |
| Anna Cloud Agent install and invoke | BLOCKED / NOT TESTED | A Console cut and valid archives do not prove fresh cloud installation, describe handshake, tool invocation or reverse Sampling at runtime. |
| Agent Session lifecycle | NOT REQUIRED FOR CURRENT FLOW; NOT LIVE-TESTED | Current UI uses single-turn LLM completion for interpretation. Anna guidance recommends Agent Session for multi-turn task continuity, cancellation and recovery; do not add Session complexity unless the product adds an ongoing multi-turn workflow. |
| APS persistence | SOURCE-INSPECTED; LIVE ACCEPTANCE PENDING | The app uses App-scope approvals and persistent policy/audit/history controls. Live APS ETag conflict behavior, concurrent writes, restart recovery and user isolation still require a Cloud Agent acceptance test. |
| Wallet execution | NOT TESTED IN THIS RELEASE | No wallet was connected and no funds were moved. Native USDC hand-off remains conditional on an injected EIP-1193 wallet; other networks remain policy/authorization-only in this app release. |

## Required acceptance gates before calling this 100% ready

1. Re-run PR CI after commit 25d6b06 and require every job to pass. Do not treat the previous failed run as green.
2. Inspect the final immutable App 0.1.34 and Executa 0.1.20 metadata together; verify the frozen tool ID and platform assets match the second profile.
3. Install the App on a clean Anna Cloud Agent using the second profile. Capture the actual Agent/runtime identity and prove Executa installation and describe.
4. Invoke a read-only method first (policy summary), then run controlled ALLOW/WARN/BLOCK scenarios. Confirm direct tool calls cannot bypass the UI-created one-time approvals.
5. Exercise APS read/write with ETag, stale if_match, concurrent update, refresh/reconnect, and user isolation. Record exact request/response evidence; no secrets in logs.
6. Test the reservation lifecycle with deterministic fixtures: ALLOW reserves; verified REJECTED and ABORTED release; UNKNOWN and SUBMITTED remain reserved; forged, mismatched and replayed receipts do not release.
7. Only after the above pass, run a wallet hand-off test. Use a tiny amount on a test environment where possible; require explicit user authorization before any real-value transfer.
8. Restore and verify the local checkout identity for the first Anna profile before any further upload. The first profile must remain untouched.

## Interpretation of Anna guides

- Build on Anna 101: the required chain is UI → Anna Runtime → Executa → reverse Sampling → Anna LLM. Source/CI validation is not a substitute for a live invocation.
- Build on Anna 102: protocol describe, manifest parity, platform artifact entrypoints and actual Cloud Agent installation are release gates.
- Build on Anna 103: use llm.complete for isolated single-turn interpretation; use Agent Session only for ongoing multi-turn tasks requiring continuity, cancellation or recovery. Session TTL does not replace durable application storage.
- APS guide: KV is for small state; Files for durable files; Host Upload is temporary transfer. ETag/if_match conflict handling and per-user isolation need live verification.

## Current decision

**NOT 100% READY.** Source and immutable Console upload are complete. Post-fix CI and live Cloud Agent/APS acceptance remain blockers. Do not connect Desktop Commander or spend Anna tokens until the CI gate is green and a compact cloud test plan is ready. Do not submit for review or publish yet.
