# Anna App pre-release inspection — 2026-11-13

Scope: Verigate Authority App 0.1.34 / bundled Executa 0.1.20, Anna App ID 851, Executa ID 1314. This is a source, CI and Console-state inspection. No Desktop Commander session, Anna Cloud Agent, wallet, or paid token-consuming test was used.

## Evidence status

| Area | Status | Evidence / boundary |
|---|---|---|
| App source and manifest | PASS (source inspection) | App manifest 0.1.34; schema-4 UI bundle; bundled Executa handle declared. |
| Executa binary distribution | PASS (build/package evidence) | Run 43376084717 built, extracted, smoke-tested and checksummed all four platform artifacts for Executa 0.1.20. |
| Executa Console version | PASS (Console metadata) | Executa ID 1314, immutable version ID 1086, version 0.1.20; four platform asset hashes recorded in Console metadata. |
| App Console cut | PASS (Console metadata) | App ID 851, immutable version ID 2182, version 0.1.34; frozen Executa 0.1.20; UI bundle status ready. App remains Draft and unpublished. |
| Manifest/runtime parity | PASS (CI) | PR #59 HEAD `b51b7114a874a41fe62491ff451e35ffcbf42cb2`; Actions run [43381228492](https://github.com/rudimentall1/verigate/actions/runs/43381228492) succeeded. Jobs `test`, `container`, `anna-ui`, and `contracts` all passed. Strict manifest parity regression test remains enabled. |
| Executa protocol source | PASS (source/CI only) | Protocol 2.0 initialize, describe, health, invoke, JSON-RPC error handling, reverse-RPC response routing and stdin loop are present; CI/container jobs pass. No fresh Anna-host handshake has been captured. |
| App approval gate | PASS (source tests with fake APS) | One-time App-scope approval is bound to invocation fields and consumed with ETag `if_match`; test fake enforces App scope and stale-ETag failure. This is not live APS proof. |
| Reservation lifecycle | PASS (local automated tests) | Tests cover ALLOW reserve, verified signed REJECTED/ABORTED release, UNKNOWN/SUBMITTED retention, forged/missing nonce rejection, approval binding, idempotency and conflict. Negative receipt trust scope is `wallet_outcome_self_report`, not wallet-signed or independent chain confirmation. |
| Anna Cloud Agent install/invoke | NOT TESTED | No clean Agent install, actual host describe handshake, live read-only tool call or live invocation evidence for App 0.1.34 / Executa 0.1.20. |
| APS live behavior | NOT TESTED | Live ETag conflict, concurrent writes, refresh/reconnect recovery and per-user isolation remain unverified. Existing authorization tests use FakeAPSStorage. |
| Wallet / chain execution | NOT TESTED IN THIS RELEASE | No wallet was connected and no funds moved. A signed self-report is not proof of chain settlement. |
| Marketplace | NOT RELEASED | App remains Draft; `is_published=false`; no review candidate. No review submission or publication was performed. |

## Remaining acceptance gates

1. Install App 0.1.34 on a clean Anna Cloud Agent in the second profile. Capture Agent/runtime identity and confirm Executa 0.1.20 installation and successful `describe`.
2. Invoke a read-only policy summary first, then controlled ALLOW/WARN/BLOCK cases. Confirm direct tool/chat calls cannot bypass UI-created one-time approvals.
3. Exercise live APS App-scope get/delete with ETag, stale `if_match`, concurrent consumption, refresh/reconnect and user isolation. Preserve request/response evidence without secrets.
4. Run a controlled wallet hand-off only after the read-only and policy gates pass. No real-value transaction without explicit user authorization.
5. Re-check that local profile identity still points to the first profile before any future upload. Do not touch App ID 382.

## Scope decision

The current product flow is single-turn. Use `llm.complete`; do not add Agent Session unless a real multi-step workflow with continuity, cancellation or recovery is introduced. Durable state remains APS-backed.

**Decision: NOT 100% READY.** Source and CI are green, and the immutable Console cut exists, but live Cloud Agent and APS acceptance remain blockers. Do not connect Desktop Commander or spend Anna tokens until the compact live test plan is ready. Do not submit for review or publish yet.
