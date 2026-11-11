# Verigate Session Checkpoint

**Updated:** 2026-11-11 14:50 +05:00  
**Repository:** rudimentall1/verigate  
**Default branch:** main  
**Current main HEAD:** 1889963944756e271c968542bdf750c272c0c874  
**Merged PR:** https://github.com/rudimentall1/verigate/pull/53  
**Merged source HEAD:** 7e7a3fc49af3e96a864ff06d0496be168794bafb

## 1. Current repository state

PR #53 was squash-merged into main on 2026-11-11. GitHub confirms main is identical to merge commit 1889963944756e271c968542bdf750c272c0c874.

The exact PR source HEAD 7e7a3fc49af3e96a864ff06d0496be168794bafb passed all four CI jobs in run #42995150968:
- test: success
- contracts: success
- container: success
- anna-ui: success

CI run: https://github.com/rudimentall1/verigate/actions/runs/42995150968

This proves the PR head passed CI before merge. A separate post-merge main-branch CI result has not yet been verified. Do not describe main CI as green until that run is checked.

PR #53 merged 46 files (4,995 additions, 178 deletions). Its scope includes Arc Registry integration, external agent SDK, Arc wallet client, API default-deny, signed-intent enforcement, Docker production defaults and container smoke tests.

PRs #38, #40, #41 and #42 were closed as superseded by #53. Their changes were reconciled into #53; they were not merged independently.

## 2. Arc integration now in main

Included:
- Arc Authority Registry Solidity contract.
- Arc-specific authorization, registration confirmation and consumption confirmation API lifecycle.
- Signed Arc payment ActionIntent bound to sender, recipient, token, amount, chain and transfer calldata.
- Identity, capability and deterministic policy checks before executable authority is issued.
- Generic execution-consume route rejects Arc authorizations.
- Verification of transaction, receipt, calldata, sender, destination, full 32-byte event topic, Registry state, block hash and timestamp.
- Local one-time authorization consumption only after on-chain Registry consumption is confirmed.
- EIP-1193 wallet client; payment broadcast remains a separate explicit user action.
- External Agent SDK, public-only enrollment package, operator enrollment/revocation script, HTTP client and runnable example.
- Late confirmation regression: HTTP confirmation may arrive after expiry only if canonical Arc inclusion time was within the signed interval.
- Evidence attribution separates Registry deployment, Guardian v3 payment evidence and any future Verigate-authorized payment.

## 3. Arc finality and performance

Registry verification:
1. Fetch receipt inclusion block by number.
2. Verify its hash against receipt block hash.
3. Fetch RPC block tagged finalized.
4. Require inclusion height <= finalized head.
5. If finalized head equals inclusion height, require matching hashes.
6. Fail closed if finalized tag is unsupported or malformed.

Arc deterministic finality is a settlement property of Arc. Verigate cannot honestly claim settlement finality faster than the chain.

Separate performance targets:
- local policy/identity/signature authority decision p95 <100 ms;
- server-side pre-broadcast path p95 <500 ms, excluding user approval, wallet signing, RPC inclusion and Arc consensus finality.

These are targets only. No benchmark has been completed.

## 4. Runtime bytecode pinning

Arc integration requires VERIGATE_ARC_REGISTRY_CODE_HASH and compares the deployed runtime bytecode Keccak-256 hash with the expected value. Missing or mismatched hash fails closed. The verification script also checks chain ID, Registry owner, enabled issuer and finalized head.

Added:
- pycryptodome dependency for Keccak-256;
- reproducible contract compile/hash script;
- read-only scripts/verify_arc_deployment.mjs.

**Still outstanding:** run the read-only verification script against Arc Mainnet, independently record the deployed runtime hash and configure VERIGATE_ARC_REGISTRY_CODE_HASH in the intended service environment. Do not claim bytecode pinning is operational until all three steps are complete.

## 5. Production security status and limitations

Implemented in main:
- Protected API routes deny by default when API keys are not configured.
- Insecure local development requires both VERIGATE_ENV=development and VERIGATE_ALLOW_INSECURE_DEV_MODE=1.
- Executable authority requires agent-signed intents outside explicit local development opt-in.
- Docker defaults to production mode, API authentication, signed intents and encrypted issuer keys.
- Compose requires API key and issuer-key passphrase and binds the service to 127.0.0.1.
- Container CI validates Compose, builds the image and tests 401 without key / 200 with valid key.

Open risks:
1. Issuer keys remain local-file based. Encryption at rest does not protect a compromised running host. KMS/HSM or isolated signing service is not implemented.
2. Complete issuer-key rotation and emergency-revocation workflow is missing.
3. Registry owner/issuer governance needs multisig/timelock or equivalent operational protection.
4. Registry is not escrow and does not block direct out-of-band wallet transfers; it enforces the integrated Verigate execution path only.
5. Trusted handlers may create transitive child side effects outside the directly observed execution boundary.
6. SQLite is single-process storage; multi-replica operation needs shared transactional storage or a production database.
7. Volumetric DoS and high-concurrency load testing are incomplete.
8. No live Arc RPC verification of finalized-tag and runtime-bytecode checks has been completed on the merged main.
9. No independent penetration test or third-party security audit.
10. No Verigate-authorized Arc registration/consumption/USDC payment has been independently verified.
11. Recovery semantics after on-chain Registry consumption but local persistence failure need dedicated tests and an explicit recovery policy.

## 6. Arc deployment facts — historical, user-confirmed

- Arc Mainnet chain ID: 5042.
- Registry: 0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D.
- Deployment tx: 0xe85784e81ca0069410e8555961c8403fa02adc1361c7455657106afc96855ebb.
- Block: 30012679.
- Owner/executor: 0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C.

These are historical user-confirmed facts and have not been freshly reverified in this session.

Transaction 0xd781e8b04b5ca89c3a34fcec50a6636049f7647d2b0e1b2bb64d5b1ee54daadf belongs to Agentic Wallet Guardian v3, not Verigate. Never attribute it to Verigate.

## 7. Remaining open pull requests — audit status

There are 8 open PRs remaining:

- **#37 — Snapshot complete server Verigate project.** 89 changed files, 17,682 additions, 81 deletions; branch diverges from main (3 commits ahead, 524 behind). It contains a large server snapshot, dated checkpoint material, backup files named *.before-*, and generated Solidity build artifacts. Do not merge this branch wholesale. Treat it as a recovery/reference source; extract only individually reviewed, still-missing functionality into a fresh branch based on current main.
- **#16 — Anna router-gated EVM wallet execution.** 71 changed files; branch diverges from main (2 commits ahead, 82 behind). It contains substantive Anna app/Executa, authority, persistence, binary packaging and tests. Do not merge the stale branch directly. Review and port only changes still absent from current main. Real Anna Cloud Agent acceptance and durable issuer-key/SQLite persistence remain explicit blockers.
- **#18 — Anna Executa response-envelope parsing.** Separate targeted UI/backend-envelope fix. Check whether its exact behavior is already included in #16 or main before porting.
- **#19 — Anna embedded-WebView confirmation UI.** Separate targeted confirmation overlay fix. Check dependency/order with #18 and current main before porting.
- **#25 — Guardian Arc agent bootstrap script.** Review against the operator enrollment functionality now merged in #53; likely overlapping, but do not close until behavior is compared.
- **#28 — Anna 0.1.18 release checkpoint.** Docs-only. Preserve release evidence and limitations; check whether its checkpoint remains current.
- **#14 — Render deployment runbook.** Docs-only pre-deployment runbook. Preserve if still accurate; no Render service or paid resource is implied.
- **#13 — PortalDot Substrate one-time consumption.** Independent PortalDot integration. It only authorizes one-time consumption and does not broadcast Substrate transactions. Keep separate from Arc work.

No other open PRs were closed.

## 8. Next actions — strict order

1. Verify the post-merge GitHub Actions run for main commit 1889963944756e271c968542bdf750c272c0c874. If no run exists, inspect workflow triggers and run the appropriate CI without changing code unnecessarily.
2. Run npm run verify:arc-deployment against Arc Mainnet using read-only RPC access. Record runtime hash, owner, issuer status, chain ID and finalized head. Do not broadcast transactions.
3. Configure VERIGATE_ARC_REGISTRY_CODE_HASH only after independent verification and explicit approval for the target environment.
4. Add recovery tests for on-chain consumption followed by local DB failure, replay/race, identity tampering and direct execution bypass.
5. Add reproducible latency benchmark reporting p50/p95/p99 without weakening authorization checks.
6. Audit #37 for unique valuable modules versus current main; no bulk merge.
7. Reconcile #16, #18 and #19 as a coherent Anna workstream; do not merge the stale 174-commit branch blindly.
8. Compare #25 with the merged enrollment CLI and decide whether it is redundant.
9. Keep #13 as a separate PortalDot task.

## 9. Hard boundaries

- No force-push or blind merge of stale branches.
- No production server deployment/restart.
- No Registry redeployment or owner/issuer changes.
- No private-key export or wallet broadcast.
- No fabricated live payment evidence.
- No claim of unhackable, fully audited, global wallet firewall or faster-than-Arc-finality behavior.
