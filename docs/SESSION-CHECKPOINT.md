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

## Final local verification

- Full Python suite: 551 passed, 4 skipped, 3 upstream deprecation warnings (117.21s), after all source/schema migration changes.
- Post-alignment contracts/protocol/binary/workspace/migration subset: 46 passed. Evidence Graph migration tests: 2 passed, including a simulated mid-migration DDL failure that proves rollback preserves the old table and data.
- Clean npm ci from package-lock.json installed 383 packages.
- Final Anna UI E2E: 38/38 passed after clean install and after final listing/security-scope edits. The real App bundle and actual Python Executa subprocess are run; only the Anna host Sampling response is mocked. No Anna CU is consumed.
- EVM atomic tests passed: stale authorization reverted with zero side effect; fresh authorization produced one side effect.
- EVM guard access-control tests passed: zero executor, attacker, stale executor state and value mismatch rejected; exact value forwarded.
- Anna CLI 0.1.64 / dispatcher 0.33.0 `validate --strict`: passed without warnings after final version and listing edits.
- `git diff --check`: passed; Git emitted only LF/CRLF normalization warnings.

## Frozen Windows artifact

- Executa 0.1.14 built with PyInstaller 6.22.3, packaged, extracted and passed anna/smoke_package.py after the SQLite migration change.
- Smoke covered describe, deterministic ALLOW, signed receipt, mock reverse-Sampling handshake, one-time App approval and wallet hand-off.
- File: anna/executas/verigate-authority/dist/verigate-authority-0.1.14-windows-x86_64.zip
- SHA-256: f3c7c32930a00f25b7e31d9c5371d0e1167fa307a671b133240839acaa34c779 (confirmed independently with Get-FileHash).
- Linux x86_64, macOS ARM64, macOS Intel 0.1.14 artifacts and exact-SHA GitHub CI are still pending. Historical CI/artifacts for 0.1.13 are not evidence for this candidate.

## Anna and hackathon limitations

- Authenticated Anna CLI last showed App ID 382, status PENDING_REVIEW, pinned App 0.1.17 / version ID 1981. The in-review version predates PR #22 and this hardening.
- Anna CU quota is exhausted. No live LLM, Cloud Agent, or APS cloud acceptance was run. Local mock tests are not Cloud acceptance.
- Real Cloud install, Linux Executa discovery, server-side Sampling, host-attested App-scope APS, actual /data/workspace injection and restart/image-upgrade persistence remain unverified.
- Anna docs say ANNA_WORKSPACE_DIR maps to /data/workspace on Cloud Agents, surviving process restart, suspend/wake and image upgrades; an idle Agent/volume can be reclaimed after roughly three days. SQLite/key state is not backed up transactionally to APS yet. Do not claim indefinite durability.
- Session refresh POST /api/v1/auth/refresh -> 401 is not proven fixed.
- Native USDC wallet hand-off supports Base and Ethereum only. Solana remains policy/authorization-only.
- Security scope: this is a pre-execution gate for transactions submitted through the integrated Verigate App/ExecutionRouter. It does not intercept independent transactions sent through other wallets/clients. The current on-chain AtomicStateGuard enforces an immutable executor + atomic state/value condition, but does not independently verify the per-action Ed25519 authorization. No external independent audit or KMS/HSM integration is complete.

## Next release steps

1. Review the entire source diff and explicitly stage only source/docs/tests; never stage .anna, node_modules, .pyinstaller or dist.
2. Commit and push a feature branch; open PR against integrate/anna-0.1.9-mainline. Require green CI on the exact commit.
3. Build and smoke all four Executa 0.1.14 platform artifacts; verify archive checksums, especially Linux x86_64 required for Anna Cloud.
4. Only after exact-SHA CI and all four artifacts pass, perform one Anna apps publish (push + immutable cut) for App 0.1.18 / Executa 0.1.14. This does not publish to Marketplace.
5. Inspect the created immutable App version and submit that exact version for Anna review / DoraHacks BUIDL. Do not call apps release until Anna approval.

Program context: DoraHacks 2349 is Anna AI App Builder Program (not PortalDot). Official qualification window ends 2026-11-30; requires approved + Marketplace-published functional App and 200 Qualified App MAU in one calendar month. The public BUIDL ID/status for Verigate has not been confirmed. The user's Anna CU quota is exhausted, so live Cloud testing is not available.

Official references:
- Build on Anna 101: https://forum.anna.partners/t/build-on-anna-101/228
- Anna 1.1.0 / CLI 0.1.64 changelog: https://forum.anna.partners/t/anna-1-1-0-beta-211-beta-220-anna-ai-cli-0-1-64-permission-gates-are-gone-manifest-schema-4-shared-node-22-chrome-runtime-for-executas-async-invoke-reliability-overhaul-faster-app-opens-harness-tools-fixed/542
- Anna review timeline: https://forum.anna.partners/t/app-review-timeline-process/318
- Anna program rules: https://forum.anna.partners/t/turn-your-ai-agents-apps-into-recurring-monthly-grants-join-the-anna-ai-os-founding-builder-program-up-to-80k-month-pool/205