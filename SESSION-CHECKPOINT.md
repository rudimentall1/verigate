# Verigate Session Checkpoint

**Updated:** 2026-11-12 10:42 +05:00
**Repository:** rudimentall1/verigate  
**Default branch:** main  
**Latest product merge before this checkpoint refresh:** 6ab3a289c300cb6d614d27bb7134ae251f7db261  
**Merged PRs:** https://github.com/rudimentall1/verigate/pull/53 and https://github.com/rudimentall1/verigate/pull/54  
**Latest merged source HEAD:** a14fb49b411e6fd18c5b74d11e85f3eb9d22fa18

## 1. Current repository state

PR #53 was squash-merged into main on 2026-11-11 as 1889963944756e271c968542bdf750c272c0c874. PR #54 was then squash-merged as 6ab3a289c300cb6d614d27bb7134ae251f7db261. The current checkpoint refresh is being committed after those product merges.

The exact PR source HEAD 7e7a3fc49af3e96a864ff06d0496be168794bafb passed all four CI jobs in run #42995150968:
- test: success
- contracts: success
- container: success
- anna-ui: success

CI run: https://github.com/rudimentall1/verigate/actions/runs/42995150968

This proves the PR head passed CI before merge. A separate post-merge main-branch CI result has not yet been verified. Do not describe main CI as green until that run is checked.

PR #53 merged 46 files (4,995 additions, 178 deletions). Its scope includes Arc Registry integration, external agent SDK, Arc wallet client, API default-deny, signed-intent enforcement, Docker production defaults and container smoke tests. PR #54 merged the Anna WebView-safe confirmation overlay and E2E harness updates (4 files, 60 additions, 56 deletions).

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

There are 5 open PRs remaining:

- **#37 — Snapshot complete server Verigate project. CLOSED as historical snapshot.** Its Valta, governance, evidence, tenancy and authority-graph modules were byte-for-byte identical to main. Its API/schema/storage/engine files were older than main; backup files and generated Solidity artifacts were not ported. Branch retained.
- **#16 — Anna router-gated EVM wallet execution. CLOSED as superseded by current main.** Anna App, Executa, authority, persistence, receipt and binary packaging sources in main are newer or equivalent. Real Anna Cloud Agent acceptance and durable Cloud persistence remain unverified.
- **#18 — Anna Executa response-envelope parsing. CLOSED as superseded.** MCP content[].text JSON decoding and tests are already present in main.
- **#19 — Anna embedded-WebView confirmation UI. CLOSED as superseded by merged PR #54.**
- **#25 — Guardian Arc agent bootstrap script.** Review against the operator enrollment functionality now merged in #53; likely overlapping, but do not close until behavior is compared.
- **#28 — Anna 0.1.18 release checkpoint.** Docs-only. Preserve release evidence and limitations; check whether its checkpoint remains current.
- **#14 — Render deployment runbook.** Docs-only pre-deployment runbook. Preserve if still accurate; no Render service or paid resource is implied.
- **#13 — PortalDot Substrate one-time consumption.** Independent PortalDot integration. It only authorizes one-time consumption and does not broadcast Substrate transactions. Keep separate from Arc work.

Other open PRs still requiring separate review: #28 Anna release docs, #25 Guardian-specific bootstrap, #14 Render runbook and #13 PortalDot Substrate consumption.

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


## 10. Latest follow-up — Anna WebView confirmation fix (2026-11-11)

PR #54 was squash-merged into main:
- Merge commit: 6ab3a289c300cb6d614d27bb7134ae251f7db261.
- Source HEAD: a14fb49b411e6fd18c5b74d11e85f3eb9d22fa18.
- CI run #42999094385 passed all four jobs: test, contracts, container and anna-ui.
- Anna UI job passed strict schema-4 manifest validation, the full UI E2E suite and Linux Executa binary build/smoke test.

The UI no longer depends on the native HTML dialog API for explicit one-time confirmation. It uses an in-app overlay, Cancel/Escape/backdrop dismissal and focus restoration. Approval storage and Executa invocation remain behind explicit Confirm.

The first PR #54 CI attempt failed because the E2E harness still queried the removed #approval-dialog element. The harness was corrected to assert #approval-overlay visibility. The subsequent exact-head CI passed. No policy, signature, wallet, nonce, storage or execution authorization rules were weakened.

PR #19 was closed as superseded by #54. PR #18 was closed because its response-envelope fix is already in main.

## 11. Post-merge validation boundary

The exact source heads of PR #53 and PR #54 passed all four CI jobs before their squash merges. A separate CI result for the resulting main branch after the latest squash commits has not yet been independently checked. Do not claim post-merge main CI is green solely from the PR-head runs.

The Arc Mainnet read-only deployment verification script remains unexecuted. No Desktop Commander device was connected in this session, so no production server command was run. No deployment, key change or transaction broadcast occurred.


## 12. Arc Mainnet read-only verification workflow — pending

PR #55: https://github.com/rudimentall1/verigate/pull/55  
Branch: `verify/arc-mainnet-readonly-2026-11-11`  
Latest branch head: `10fc288527ce1766ca22c3cf14de22c418778a6b`.

The workflow runs `npm run verify:arc-deployment` against the known Arc Mainnet Registry and executor. It performs read-only RPC calls only: chain ID, deployed runtime bytecode, owner, enabled issuer and finalized head. It uses no signer, private key, transaction submission or deployment.

A dedicated workflow file and a one-time conditional CI job were added on the PR branch to make the live verification result inspectable. GitHub's current connector has not surfaced a workflow run for this branch yet. Therefore the live verification is still **not run/verified** from this session. PR #55 remains Draft and must not be merged until a visible PASS is recorded. A runtime mismatch or unsupported finalized tag must remain a hard failure.


## 13. Checkpoint refresh — 2026-11-11 16:17 +05:00

Verified against GitHub after the prior checkpoint:

- Current `main` HEAD: `abb507b3e87131c6a87e6f3f4746c1e39ac4c7ef`.
- Post-merge main CI run `43000194992`: **success**. This closes the earlier uncertainty about whether the squash-merged main passed CI.
- PR #55 remains Draft at head `10fc288527ce1766ca22c3cf14de22c418778a6b`; it is 3 commits ahead and 2 behind main (merge base `d0f344e6ffa863f6a3ee0c19d62058232ce47f6b`).
- PR #55 workflow runs:
  - Dedicated read-only workflow run `43000038808`: failure.
  - Main CI run `43000040926`: failure.
  - Both were created and marked started/completed within approximately one second; GitHub Actions Jobs API returned zero jobs for the dedicated run, and the commit Check Runs API returned zero check runs for the PR head.
  - Both run records identify the triggering event as `push`, not `pull_request`.
- Inspected both workflow YAML files at PR head. The dedicated workflow declares push on the verification branch, path-filtered pull_request to main, and workflow_dispatch. The PR's ci.yml adds a conditional job requiring `github.event_name == 'pull_request'` and the exact head branch name. The actual recorded event for both failures was `push`, so that conditional job would not run on the recorded event. This explains why the conditional job is skipped for the ci.yml push run, but does **not** by itself explain why the dedicated push workflow produced no jobs and failed.
- No runner logs or job logs exist for these two runs. Root cause of the pre-job failure remains **unknown**. Do not claim it is an Arc RPC/script failure, and do not change workflow configuration speculatively.
- Current main `.github/workflows/ci.yml` was fetched and contains the four established jobs only; the temporary conditional Arc job exists on PR #55 branch, not on main.
- No server connection or server command was used. No RPC verification, transaction, deployment, key change or production action occurred.

### Next action

Continue investigating GitHub Actions' pre-job failure for run `43000038808` using workflow/run/check-suite metadata and the commit/event history. Do not rerun or merge PR #55 until a concrete cause is established. Once a workflow job can actually start and pass, run the read-only Arc Mainnet verification and record runtime bytecode hash, owner, enabled issuer and finalized head. Keep live verification status **not run / not independently verified** until then.


## 14. Arc verification workflow diagnosis — 2026-11-11

PR #55: https://github.com/rudimentall1/verigate/pull/55

- The pre-job workflow failure was identified from the GitHub Actions annotation: unquoted `0x...` address values were parsed as YAML integers where workflow env values require strings.
- Quoted both Registry and Executor addresses in both `.github/workflows/arc-deployment-readonly.yml` and the temporary Arc verification job in `.github/workflows/ci.yml`.
- Latest PR branch head at this checkpoint: `777fb01f4e4a33e6417c94ee82e34bdeb58612d5`.
- GitHub now creates runner jobs. Read-only verifier run: [43012817343](https://github.com/rudimentall1/verigate/actions/runs/43012817343); PR CI run: [43012817755](https://github.com/rudimentall1/verigate/actions/runs/43012817755).
- The read-only verifier successfully installed dependencies, connected to Arc Mainnet chain ID 5042, retrieved deployed bytecode, then FAILED closed on exact runtime bytecode comparison:
  - compiled source hash: `0x20ee1d407229f43acb985459db74d3d0ec6d6d25782b29f9e3baf72b51284597`
  - deployed runtime hash: `0x6b229c049b9ba0007c318a10759a9827b5a798a4e511611872dcd4cf3973b160`
- Therefore owner, enabled issuer and finalized-head checks were NOT reached by this verifier. Do not claim live deployment verification PASS; do not pin/configure the chain hash; do not weaken or bypass bytecode comparison.
- PR CI run 43012817755: `test`, `contracts`, and `container` jobs passed; `anna-ui` was still running its Linux Executa binary build at checkpoint time. The separate Arc read-only job failed on the runtime mismatch.
- Current source and verifier files are byte-identical to main; current lockfile resolves solc `0.8.37`. The cause of deployed/source runtime mismatch is NOT YET ESTABLISHED. Compiler settings/version, deployment-time source revision, metadata, and actual deployment artifact must be reconciled before any code or deployment change.
- No contract deployment, transaction broadcast, key operation, server command, or runtime configuration change was performed.
- Next action: recover the exact deployment-time source/compiler settings/artifact and compare against on-chain creation/runtime bytecode. Keep PR #55 Draft and do not merge until the discrepancy is explained and the read-only verification passes or is correctly redesigned around a reviewed deployment artifact.


### Final status for PR CI run 43012817755

- Completed: `test` PASS, `contracts` PASS, `container` PASS, `anna-ui` PASS.
- Failed: `Arc Mainnet deployment verification (read-only)`, solely at the runtime bytecode comparison described above.
- Overall PR CI conclusion: FAILURE because the read-only Arc verification correctly fails closed on the mismatch.


## 15. Arc Mainnet transaction evidence clarification — 2026-11-11

This section corrects the interpretation of the two transaction hashes discussed during the checkpoint recovery. The user supplied an Arc Explorer screenshot of the executor EOA transaction list:
https://explorer.arc.io/address/0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C?tab=txs

The screenshot visibly lists the following distinct transactions:

1. **Registry deployment**
   - Transaction: `0xe85784e81ca0069410e8555961c8403fa02adc1361c7455657106afc96855ebb`
   - Explorer type: `Contract creation`
   - Block: `30012679`
   - Created contract shown by Explorer: `0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D`
   - This is the Registry deployment transaction. The prior checkpoint's deployment hash, address and block were correct.

2. **USDC approval**
   - Transaction: `0x4c1926681405885ff6e99a15aa73f9bbe8eb895a1eea33455efd0a73e8745c18`
   - Explorer type: `Contract call`
   - Method: `approve`
   - Destination shown: USDC token contract
   - Block: `30013066`
   - This is an ERC-20 approval call, **not** the Registry deployment and not proof of a Verigate-authorized payment or settlement. Explorer displays transaction value 0 and fee 0.00142753 USDC.

The same screenshot also lists later contract calls from the executor to the Registry at blocks 30024727, 30025935 and 30026205. Their presence is visible, but their exact semantic outcome must be established from transaction input, receipt logs and Registry state before describing them as successful registration or consumption confirmations.

### Evidence classification

- The deployment transaction, Registry address and deployment block are now corroborated by the user-provided Arc Explorer screenshot, in addition to the historical checkpoint record.
- The approval transaction is separately identified by Explorer as an `approve` call.
- This screenshot is explorer UI evidence. It is not a fresh independent RPC verification of runtime bytecode, owner, issuer state or finalized head.
- The runtime bytecode mismatch reported in section 14 remains a separate unresolved verification issue:
  - compiled source hash: `0x20ee1d407229f43acb985459db74d3d0ec6d6d25782b29f9e3baf72b51284597`
  - deployed runtime hash: `0x6b229c049b9ba0007c318a10759a9827b5a798a4e511611872dcd4cf3973b160`
- The mismatch does **not** invalidate or make uncertain the fact that the Registry deployment transaction is recorded as a successful contract creation in block 30012679. It means the current source build has not yet been proven byte-for-byte equivalent to the deployed runtime.

### Correct working interpretation

Do not refer to `0x4c192668...` as the deployment hash. Use `0xe85784e8...` for Registry deployment and `0x4c192668...` for the USDC approval. Keep the runtime artifact investigation open; do not redeploy, change the expected code hash, or weaken the verifier to make the mismatch disappear.

No server command, contract call, transaction broadcast, deployment, key operation or production configuration change was performed while adding this checkpoint clarification.


## 16. Arc Registry deployment artifact recovered and independently re-verified — 2026-11-12

### Root cause of the earlier runtime mismatch

The earlier read-only verifier rebuilt the current `main` Solidity source and compared that output with the immutable Arc Mainnet deployment. This was the wrong comparison baseline.

The original deployment source and Foundry artifact were recovered from the retained historical `integration/arc` ref:

- Deployed source blob: `adf46b928ee82ffc780a7f238272defcfeb73d8b`.
- Original Foundry artifact blob: `11f7a16698f680c4e66f6d37786249f703e63faa`.
- Original compiler: Solidity `0.8.24+commit.e11b9ed9`.
- EVM target: `cancun`.
- Optimizer: enabled, 200 runs.
- `viaIR`: false.
- Metadata: IPFS bytecode hash, CBOR appended, literal source content disabled.
- Metadata source unit: `src/VerigateAuthorityRegistry.sol`.
- Deployed source expiry boundary in `consumeAuthorization`: `block.timestamp <= auth.validUntil`.
- Current `main` source expiry boundary: `block.timestamp < auth.validUntil`.
- Current npm compiler range: `^0.8.37`; previous verifier did not explicitly set the historical EVM target or use the historical source-unit name.

The source's locally computed Keccak-256 exactly matches the compiler metadata source hash:
`0x117126830a75b649615e382998b63312958e1f7cc64c4c98a356192f8095c684`.

The recovered runtime artifact is 3,119 bytes. Its Keccak-256 is:
`0x6b229c049b9ba0007c318a10759a9827b5a798a4e511611872dcd4cf3973b160`.

That runtime hash is an exact match for the deployed runtime hash previously returned by Arc RPC in run #43012817343. The previous mismatch was caused by comparing different source/compiler builds; it was **not** evidence that the Registry had not deployed or that the deployment transaction was wrong.

### Recovery committed for review in PR #56

Draft PR: https://github.com/rudimentall1/verigate/pull/56  
Branch: `fix/arc-deployment-artifact-verification-2026-11-12`  
PR head at creation: `31bad4d8b86c47fdef10e990a15046303840311f`  
Base: `main` at `20c7e666ed697ae8f59c6d43541a6f84f1237818`.

The PR adds:
- `contracts/arc-authority/deployments/arc-mainnet/VerigateAuthorityRegistry.deployed.sol`: exact historical source snapshot.
- `contracts/arc-authority/deployments/arc-mainnet/VerigateAuthorityRegistry.runtime.hex`: exact recovered runtime bytecode.
- `contracts/arc-authority/deployments/arc-mainnet/deployment-manifest.json`: chain, deployment, owner, compiler, source and artifact identity.
- `docs/evidence/arc-registry-deployment-artifact.md`: provenance, explanation and semantic boundary.
- Updated `scripts/verify_arc_deployment.mjs`: checks the reviewed deployment artifact instead of compiling the current source as a substitute.
- Dedicated read-only workflow `.github/workflows/arc-deployment-readonly.yml`.

The PR remains **Draft and not merged**. Do not merge without explicit user authorization.

### Latest Arc Mainnet read-only verification — PASS

Workflow run: https://github.com/rudimentall1/verigate/actions/runs/43159111792  
Run ID: `43159111792`  
Job: `Verify Arc Registry deployment (read-only)` — success.

The workflow verified against Arc Mainnet:
- Chain ID: `5042`.
- Registry: `0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D`.
- Deployment transaction exists and is a contract creation from the expected executor.
- Receipt status: success.
- Deployment block: `30012679`.
- Receipt-created contract address matches the Registry address.
- Canonical deployment block hash: `0x5a427573baecb8f86bfe1a79ed2284958418b4299c4111efd1489eba8fb51213`.
- Registry owner: `0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C`.
- Configured executor is an enabled issuer: `true`.
- Finalized head at verification time: block `30807542`, hash `0x53be70a53ea8f0c82b0e1939a80a484cfa6db0dd2be8666025a41f078ad7a63d`.
- Recovered artifact runtime hash equals the deployed on-chain runtime hash:
  `0x6b229c049b9ba0007c318a10759a9827b5a798a4e511611872dcd4cf3973b160`.

### PR #56 CI status

CI run: https://github.com/rudimentall1/verigate/actions/runs/43159111732  
All four jobs completed successfully:
- `test`: PASS.
- `contracts`: PASS.
- `container`: PASS.
- `anna-ui`: PASS, including strict manifest validation, UI E2E and Linux Executa binary build/smoke.

The dedicated Arc read-only workflow also passed. These CI and RPC checks apply to the PR #56 merge ref / branch content, not to a production deployment of the Verigate API service.

### Security and deployment boundaries

- The deployed Registry's on-chain exact-expiry boundary is inclusive (`<=`). The current API integration separately rejects inclusion timestamps `>= valid_until`; therefore the supported Verigate flow remains strict at the API verification layer. Do not claim that the immutable deployed contract itself has the newer `<` condition.
- The Registry is an authorization/evidence mechanism, not escrow or a global wallet firewall.
- The recovered code hash is now established as the reviewed artifact hash. It has **not** been installed into a production service environment.
- Do not update production `VERIGATE_ARC_REGISTRY_CODE_HASH`, deploy/restart the server, alter owner/issuer state, or broadcast transactions without a separate explicit decision.
- No server command or production change was made during this recovery.


## 17. Arc Registry historical lifecycle evidence — 2026-11-12

### Historical Registry calls verified

The three calls visible in the user-provided executor address screenshot were independently resolved through Arc RPC. The verifier checks each transaction in its reported block, sender, destination, selector, successful receipt, receipt/canonical block hash, Registry-emitted event and stored Registry state. Each activity block was also required to be at or below the finalized head.

1. **Registration — block 30024727**
   - Transaction: `0xa6a2fb23af073085c64bb168f14ee02d90d64fbeb4629dc2724ba1d01624867f`
   - Method/event: `registerAuthorization` / `AuthorizationRegistered`
   - Authorization ID: `0x3c67a35b4d370c8f80a221270fcfebcf0eba20b6bad478e2761809daab2b7299`
   - Intent hash: `0xfa87d4962e3a9e260ca77d98b9b3197f759388412a24f505ce6e1eb9bb0448cd`
   - Registry state at verification: registered, not consumed, not revoked.

2. **Registration — block 30025935**
   - Transaction: `0x5f45d89e0f12e42a0d00268d6125a2b05f6474f4ed786895bc7715cf39ad1696`
   - Method/event: `registerAuthorization` / `AuthorizationRegistered`
   - Authorization ID: `0xc208b44433c17dbe4e71aea589f5755b1408e37d46a522c1f2022592ed2fdec2`
   - Intent hash: `0xf17c1a8a37add7e8d9af4a2f750e3035bcc4daa22e09ea03368acb747c1b9181`
   - Registry state at verification: consumed, not revoked.

3. **Consumption — block 30026205**
   - Transaction: `0xc0b2a5de7973da979808ebf5f69e4736ad1eea22fc1fdd5f698b2b44cbad5de8`
   - Method/event: `consumeAuthorization` / `AuthorizationConsumed`
   - Authorization ID and intent hash match the second registration exactly.
   - Registry state confirms `consumed=true`, `revoked=false`.

These transactions prove two successful Registry registrations and one successful one-time Registry consumption. They do **not** establish that the associated off-chain authorization packages were produced by the Verigate API, and they do not show a USDC transfer or settlement. Do not describe this as a completed Verigate-authorized payment.

### Latest verification and CI

Latest read-only Arc verification: [run 43160472757](https://github.com/rudimentall1/verigate/actions/runs/43160472757) — **PASS**.

- Runtime bytecode hash equals the recovered reviewed artifact:
  `0x6b229c049b9ba0007c318a10759a9827b5a798a4e511611872dcd4cf3973b160`.
- Deployment transaction, successful receipt, Registry address, deployer, block 30012679 and canonical deployment block hash verified.
- Owner and enabled issuer verified.
- Historical activity receipts, events and state verified.
- Finalized head at this run: block `30808953`, hash `0x43686ce3625f2115ef3d269d627c98bbb75976993479d3585b2f3867c76dd5e1`.

Full CI for the current PR merge ref: [run 43160472728](https://github.com/rudimentall1/verigate/actions/runs/43160472728) — all four jobs **PASS**:
- `test`
- `contracts`
- `container`
- `anna-ui`, including the Linux Executa build and smoke test.

### PR status and boundaries

- PR #56: https://github.com/rudimentall1/verigate/pull/56
- Current PR head: `677fd00552d828c52b3008d9eddf0f77a244e016`.
- PR remains **Draft**, open and unmerged. CI and read-only verification are green; do not merge without explicit authorization.
- PR #56 updates deployment evidence and verification only. It does not deploy the Verigate API service.
- `VERIGATE_ARC_REGISTRY_CODE_HASH` has not been installed in a production environment.
- No Gensyn2 server command, service restart, owner/issuer mutation, contract deployment or transaction broadcast occurred.


## 18. npm dependency audit warning observed in PR #56 CI — 2026-11-12

The contract-tooling CI job for PR #56 completed successfully, but `npm ci` reported that it audited 420 packages and found:

- 1 low
- 5 moderate
- 25 high
- 5 critical

This is an npm dependency-tree advisory count, not yet a confirmed count of vulnerabilities reachable in a shipped production runtime. The job installs the repository's npm contract/test tooling and related transitive packages. The individual advisories, vulnerable package paths, direct/transitive status, fix availability and whether any affected package ships with an executable product have **not yet been triaged**.

Next security action: capture `npm audit --json`, identify the exact affected dependency paths, separate build/test-only packages from shipped runtime dependencies, then plan minimal compatible updates and rerun the full CI. Do not run `npm audit fix --force` blindly and do not report this as 36 confirmed production vulnerabilities.

Evidence source: [PR #56 CI run 43160472728](https://github.com/rudimentall1/verigate/actions/runs/43160472728), contract-tooling job installation output.

No dependency update or remediation was made in this session.


## 19. npm dependency audit triage — 2026-11-12

### Exact audit result

A dedicated non-blocking audit report was added temporarily to the PR #56 Arc read-only workflow to capture full npm advisory metadata.

Audit result: 420 packages; 36 advisories:
- 5 critical
- 25 high
- 5 moderate
- 1 low

All four root dependencies in `package.json` are declared under `devDependencies`:
- `ethers`
- `ganache`
- `jsdom`
- `solc`

Therefore this particular npm tree is the contract/test tooling dependency tree, not the Python API's production runtime dependency set. The advisories still matter to developer machines and CI, but they must not be reported as 36 confirmed production API vulnerabilities.

### Root cause concentration

The majority of the advisories are nested under `ganache@7.9.2`. The audit identifies critical advisories in bundled transitive packages including `cipher-base`, `elliptic`, `pbkdf2`, `sha.js` and `webpack`, alongside high-severity issues in other bundled dependencies.

The npm dry-run explicitly reports that bundled dependencies `bn.js`, `elliptic` and `secp256k1` inside Ganache cannot be fixed automatically and recommends checking for an updated Ganache package. The audit's suggested Ganache remediation is a SemVer-major change and must not be applied blindly.

A separate direct dependency finding affects `solc` through transitive package `tmp@0.2.6`. The dry-run preview proposes `solc 0.8.37 -> 0.8.38` and reports two packages changed in its isolated preview. No package or lockfile was actually modified by this dry run.

### Usage and scope

- `ganache` is imported by local contract/guard test and compile scripts; it is not imported by the Verigate API runtime.
- `solc` is used by contract compilation/test scripts; it is not imported by the API runtime.
- The Python API runtime dependency set is separately defined in `requirements.txt`.

### Decision

Do not use `npm audit fix --force` and do not downgrade Ganache to the suggested major-incompatible version.

Next safe dependency action:
1. Validate `solc@0.8.38` against the current contract compile and all CI jobs before committing the lockfile update.
2. Investigate a maintained replacement for Ganache or an isolated test-only toolchain migration. Do not let this dependency cleanup block the Arc production integration work.
3. Keep the Python API production dependency audit separate from this npm dev-tooling audit.

### CI evidence

- Audit report and dry-run preview were executed in [Arc read-only run 43161791635](https://github.com/rudimentall1/verigate/actions/runs/43161791635).
- Arc read-only deployment verification in that run: **PASS**.
- Full CI run [43161791702](https://github.com/rudimentall1/verigate/actions/runs/43161791702): test, contracts and container jobs passed at last inspection; `anna-ui` was still in progress.
- No dependency update, lockfile change, server change or production deployment was made.


## 20. Arc constrained signer service — 2026-11-12

### Workstream and branch

- Dedicated branch: `feat/arc-agent-signer-service-2026-11-12`.
- PR #58: https://github.com/rudimentall1/verigate/pull/58
- PR #58 is Draft/Open and stacked on PR #57 branch head `cba949600e02e8419f5bb2bc8a4fb75c5b1c4b7f`; it is not based on `main`.
- Latest implementation/test commit: `ed65caefe7238a46283eb8e48e5e1ba66645ab47`.
- Latest full passing CI before the new crash/restart tests: run [43191800554](https://github.com/rudimentall1/verigate/actions/runs/43191800554), on prior implementation head `a3d6e8f7af971abe70703b55e5e93c5fb0eac682`.
- PR #57 remains separate. Do not merge either PR without explicit approval.
- This checkpoint and all signer work are on the signer branch, not `main`.

### Implemented

1. `integrations/arc-constrained-signer.mjs`
   - Verifies pinned Verigate Ed25519 authorization signatures, version 1, positive timestamps and the 300-second validity window.
   - Accepts API-compatible bytes32 authorization IDs both with and without `0x`.
   - Validates Arc Mainnet chain 5042, canonical Arc USDC, six decimals, zero native value and exact transfer calldata.
   - Derives Registry registration, Registry consumption and USDC payment calldata internally.
   - Enforces issuer-only registration and agent-only consumption/payment.
   - Validates configured fee ceilings and live fee data.
   - Uses an append-only fsync-backed journal with locking, replay protection, cumulative per-instance daily budget reservations and fail-closed unresolved operations.
   - Journal file reads reject symlinks, hard links, foreign ownership and group/other permissions; journal directories must be owned by the signer and mode 0700.
   - Operation state is `reserved` → `broadcast` → `complete`: transaction hash is fsynced immediately after RPC submission and before receipt waiting; completion must match the durable broadcast hash.
   - Journal keys bind the canonical lowercase bare bytes32 authorization ID to the signed authorization digest. Different signed intents reusing one ID cannot share replay or consume state.
   - Agent `payment` reservation is rejected unless the same signed authorization digest has a completed `consume` receipt in that agent journal.

2. `integrations/arc-signer-socket.mjs` and `integrations/arc-signer-client.mjs`
   - Unix-domain socket only; typed operations are `register`, `consume`, and `payment`.
   - Rejects arbitrary transaction fields, oversized requests and existing socket paths.
   - Uses socket mode 0660 and a durable reservation before adapter execution.
   - Completed requests replay the saved result instead of broadcasting twice.
   - Client exposes only the three typed operations; no generic sign or send-transaction method.

3. `integrations/arc-ethers-signer-adapter.mjs`
   - Ethers v6 adapter pins Arc chain ID, a configured 20-byte Registry address and the expected Registry runtime code hash.
   - Startup checks the configured issuer mapping on-chain; issuer role also requires the loaded signer address to match the configured issuer.
   - Enforces live fee data, gas estimation, configured gas/fee ceilings, pending nonce lookup, serialized local broadcasts, receipt status/hash/sender/destination/block checks, confirmation wait and actual native-cost accounting.

4. `scripts/run_arc_signer.mjs` and `deploy/systemd/verigate-arc-signer@.service`
   - Linux-only daemon entrypoint.
   - Loads EVM private key from a protected file, checks file type, owner and restrictive permissions, and does not accept the private key through command-line arguments or environment variables.
   - Requires separate role, socket, journal, RPC, Registry, issuer, public-key and fee configuration.
   - systemd template provides separate issuer/agent users and groups, strict filesystem protection, restricted writable paths, no ambient capabilities and restricted address families.
   - Added `deploy/arc-signer/install.sh`, `rollback.sh`, role-specific `.env.example` templates and `tests/arc-signer-deploy-smoke.sh`. Installer modes are staged: `--provision-accounts`, read-only `--check`, then `--apply` to install the unit only. It never generates/imports keys or starts services. Rollback preserves keys, env files, journals, users and groups.
   - Disposable Ubuntu CI smoke test provisions temporary signer users/groups, validates key/config permissions, installs the unit with a stubbed systemctl, runs `systemd-analyze verify`, verifies no service start/enable, runs rollback and checks keys/env/journals remain. This validates filesystem, unit syntax and script behavior, not an actual systemd daemon start.
   - Installer validates root-owned env files, exact socket/journal/key paths, pinned Registry address/hash, HTTPS RPC, 20-byte issuer address, numeric fee limits, and separate signer-owned 0600 key/public-key files. Config/key parent directories are root-owned mode 0711.

5. Existing Arc executor integration
   - Added `executeAuthorizedArcPaymentWithSignerClients` to `integrations/arc-agent-executor.mjs`.
   - Preserves the existing API sequence: authorize → issuer register → registration confirm → agent consume → consumption confirm → agent payment → payment confirm.
   - Validates the API-provided transaction envelopes against independently derived calldata before requesting signer operations.
   - Orchestrator uses typed socket clients and does not load EVM Wallets or private keys.

6. Tests and CI
   - Added policy, socket server, socket client, ethers adapter and signer-client orchestration tests.
   - Added restart regression tests for both ambiguous crash windows:
     - reservation persisted but no transaction hash recorded;
     - broadcast hash recorded but receipt unresolved.
   - Both tests restart the service against the same journal and assert that the operation remains blocked and the adapter is not called a second time.
   - Full CI run [43191800554](https://github.com/rudimentall1/verigate/actions/runs/43191800554) passed 4/4 jobs (`contracts`, `test`, `container`, `anna-ui`) on prior implementation head `a3d6e8f7af971abe70703b55e5e93c5fb0eac682`. The contracts job includes the disposable Linux installer/rollback smoke test and `systemd-analyze verify`.
   - A fresh CI run for exact current head `ed65caefe7238a46283eb8e48e5e1ba66645ab47` is still required. Do not report the previous passing run as validation of the two new tests.

### Verified Registry pin

- Registry: `0x4D09CdD490c1Ce48BCB6DA5c1A6Bf41E2f5e853D`.
- Read-only deployment verification: [run 43160472757](https://github.com/rudimentall1/verigate/actions/runs/43160472757).
- The run confirmed Arc chain ID 5042, the Registry address, owner, enabled issuer, deployment transaction/block and matching deployed runtime hash `0x6b229c049b9ba0007c318a10759a9827b5a798a4e511611872dcd4cf3973b160`.
- The signer pins this exact 20-byte address and rejects a different configured value. The earlier 41-character address in a previous checkpoint note was a transcription error, not the repository's actual deployment address.

### Explicit limitations — not production-ready

- No signer keys were created, copied or exposed.
- No live Arc transaction was broadcast by this service.
- Adapter tests use mocked provider/wallet objects; they are not live-chain verification.
- The disposable Ubuntu CI smoke test validated account provisioning, installer preflight, unit installation without starting services, unit syntax and rollback. It did not start the signer under a real systemd manager.
- Actual systemd service startup/restart and issuer/agent socket ACL behavior remain unverified.
- Fee ceilings still need to be measured from representative Arc receipts and reviewed.
- Gensyn2 was not accessed or modified.
- This is OS-isolated signing, not an HSM and not protection against root/host compromise.

### Next gates

1. Obtain a fresh full CI result on exact head `ed65caefe7238a46283eb8e48e5e1ba66645ab47`; fix any failure before proceeding.
2. Independently review stale journal-lock recovery and the operator reconciliation procedure. A crash while holding the exclusive lock can leave a lock file; fail-closed behavior is intentional, but recovery must be documented and tested without deleting unresolved operation records.
3. Validate actual systemd manager startup/restart and issuer/agent socket ACLs in a disposable Linux environment. Do not use Gensyn2 for this gate.
4. Measure fee ceilings from representative Arc receipts and review the per-role budgets. The two role journals enforce separate budgets, not one shared global ceiling.
5. Only after all gates pass, inspect Gensyn2 read-only and prepare a controlled installation. Do not modify FLOP, AegisForge, OWNERA or unrelated services.
6. No mainnet transaction or production key provisioning without a separate explicit decision.


## 21. Arc constrained signer: exact-head CI and stale lock gate — 2026-11-12

### Exact-head CI verification

- Current PR #58 head: `a4a11a2501f316e257f2cdc3352840e170aa0345`.
- GitHub Actions CI run [#43193728508](https://github.com/rudimentall1/verigate/actions/runs/43193728508) is associated with that exact commit and completed with conclusion **success**.
- All four jobs passed:
  - `contracts`: includes constrained signer policy tests, signer client/orchestration tests, Arc compile/access-control tests.
  - `test`: full repository test suite, SDK/wallet client tests, end-to-end demo and API smoke check.
  - `container`: protected Compose configuration, production image build and API auth smoke test.
  - `anna-ui`: manifest validation, app/plugin E2E UI test, Linux Executa build/smoke test.
- This exact-head run supersedes the earlier note that a fresh CI run was still required for the crash/restart tests. Both restart regression tests are now covered by a successful exact-head full CI run.
- PR #58 remains Draft/Open and unmerged. PR #57 remains separate. No merge or readiness-state change was made.

### Remaining journal-lock issue

- `OperationJournal.withLock()` still creates an exclusive `.lock` file with `openSync(..., "wx")` and removes it in `finally`.
- A hard process termination can leave the lock file behind. The service correctly fails closed, but the current lock contains no owner metadata and cannot safely distinguish a live owner from a stale lock.
- No stale-lock recovery code or operator recovery command has been implemented yet.
- Next implementation must add owner identity (PID, Linux boot ID and process start ticks), fsync lock metadata, and provide explicit inspect/recover behavior. Recovery must refuse malformed/unsafe/live-owner locks, require an explicit apply flag, never run automatically at service startup, and must not alter or delete journal records.
- Add tests for live-owner refusal, stale PID/start-time detection, PID reuse protection, malformed metadata, symlink/hardlink/permission rejection, and byte-for-byte journal preservation.

### Deployment gates unchanged

- Actual systemd manager startup/restart and issuer/agent socket ACL behavior remain unverified.
- Fee ceilings still require measurement from representative Arc receipts. Issuer and agent journals have separate budgets, not one shared global budget.
- No signer keys were provisioned and no live Arc transaction was broadcast by the signer.
- Gensyn2 remains untouched. Do not modify FLOP, AegisForge, OWNERA or unrelated services.
- Do not merge PR #57 or #58, provision production keys, start signer services or send live transactions without separate explicit approval.


## 22. Arc signer stale-lock recovery implementation — 2026-11-12

### Implemented on the signer branch

- Updated `OperationJournal.withLock()` to write owner metadata into the exclusive lock file and fsync it before running the protected operation:
  - signer PID;
  - Linux boot ID;
  - Linux process start ticks from `/proc/<pid>/stat`;
  - metadata version and platform.
- Added `OperationJournal.inspectLock()`:
  - checks regular-file type, one hard link, exact 0600 permissions and signer ownership;
  - opens with `O_NOFOLLOW` where supported and checks the opened inode against the initial `lstat`;
  - rejects malformed or unsupported metadata;
  - distinguishes a live process from a stale lock using boot ID, PID liveness and process start ticks, protecting against PID reuse.
- Added `OperationJournal.recoverStaleLock({ apply })`:
  - default behavior is inspect-only;
  - requires `apply: true` to unlink a provably stale lock;
  - refuses a live owner or any uncertain/unsafe lock;
  - checks the lock inode again immediately before unlinking;
  - never reads, rewrites, truncates or deletes journal operation records.
- Added operator command `scripts/recover_arc_signer_lock.mjs` and npm alias `npm run recover:arc-signer-lock -- /path/to/journal.jsonl [--apply]`.
- Added tests for live-owner refusal, PID reuse, stale PID recovery, explicit-apply requirement, malformed metadata, symlink/hardlink/broad-permission rejection, journal byte preservation, lock owner metadata and concurrent acquisition refusal.
- Recovery is not called automatically at service startup. Non-Linux environments can continue to use the journal, but stale-lock recovery is intentionally unsupported there.

### Verification status

- Latest implementation commit at this checkpoint: `75fd812bc7495be646b7dac1bc491a99f8ba36cd`.
- PR #58 remains Draft/Open and unmerged.
- The exact-head CI pass [#43193728508](https://github.com/rudimentall1/verigate/actions/runs/43193728508) validates the previous head `a4a11a2...`, **not** the stale-lock implementation above.
- A fresh CI run for `75fd812...` has not yet appeared in the GitHub workflow-run lookup. Do not claim these new lock-recovery tests pass until the fresh run completes.
- No Gensyn2 access or changes, no signer key provisioning, no service start and no live transaction.


## 23. Arc signer recovery hardening and operator runbook — 2026-11-12

- Added `deploy/arc-signer/LOCK-RECOVERY.md` with explicit inspect-first/apply-second instructions, service-inactive precondition, expected lock states and post-recovery journal handling.
- Tightened recovery against lock replacement races: before unlinking, the code re-inspects owner liveness and metadata, verifies the original device/inode, then rechecks file type, hard-link count, exact 0600 mode and ownership.
- Latest branch implementation commit: `c8bb76ae9d543cd9f2add79d18baf37b4fc1c4f4`.
- PR #58 remains Draft/Open. No merge, service installation, key provisioning or live transaction.
- CI for the stale-lock implementation is still not confirmed. The last confirmed full CI pass remains run #43193728508 on the earlier head `a4a11a2...`. Do not mark the new lock recovery code tested until a fresh run on the current head passes.


## 24. Arc signer PR metadata and latest checkpoint — 2026-11-12

- PR #58 description now includes the stale-lock owner metadata, explicit recovery command, PID-reuse protection, unsafe-lock rejection and operator runbook.
- PR remains **Draft/Open**, based on PR #57. No merge or base change.
- Latest signer branch head: `2d080d9bc431acdad87e7ea7d2db0b1764926611`.
- Latest confirmed full CI pass remains run [#43193728508](https://github.com/rudimentall1/verigate/actions/runs/43193728508) on earlier head `a4a11a2...`. The workflow-run lookup has not returned a run for the new stale-lock commits, and combined commit status is empty. Treat the new code as **not yet CI-verified**.
- Before any deployment discussion, obtain a full CI run for the latest head and inspect the `contracts` job output for the lock recovery tests. Then test the real systemd runtime/ACL behavior in a disposable Linux VM.


## 25. Arc integration and constrained signer current state — 2026-11-12

This section supersedes earlier stale-lock, systemd and CI status statements in sections 20–24 below/above. Older entries remain as historical checkpoints, not current status.

### Pull request and branch state

- Repository: `rudimentall1/verigate`.
- PR #56: Arc Registry deployment verification evidence, Draft/Open; separate read-only deployment verification work.
- PR #57: `feat/arc-payment-settlement-confirmation-2026-11-12`, head `cba949600e02e8419f5bb2bc8a4fb75c5b1c4b7f`, Draft/Open, not merged. Adds payment settlement confirmation after an explicitly broadcast wallet payment.
- PR #58: `feat/arc-agent-signer-service-2026-11-12`, Draft/Open, not merged; stacked on PR #57's branch. Do not change Draft state or merge either PR without explicit approval.
- Latest signer code/test commit covered by the new full CI run: `dd5a44f7a31dfcc80b378aed8a3d6d8279fec5d0`. The checkpoint/docs-only follow-up commit is `9b4787030fe9ffdc4a45e8f3edbf22e5c0448769`.
- The latest full CI run associated with the implementation commit is [#43227346896](https://github.com/rudimentall1/verigate/actions/runs/43227346896). At checkpoint creation, `contracts`, `test` and `container` are **success**; `anna-ui` is still running its Executa binary smoke test. Do not call the whole run 4/4 until that final job completes.

### Newly verified implementation gates

1. **Stale journal lock recovery**
   - Lock metadata records PID, Linux boot ID and process start ticks, is fsynced and is checked against current process identity.
   - Explicit inspect-first / `--apply` recovery only; live, malformed, unsafe or uncertain locks are refused. PID reuse is checked. Lock inode/owner/mode are revalidated immediately before removal.
   - No automatic startup cleanup. The operation journal itself is never truncated or rewritten by lock recovery.
   - Test coverage includes live owner, stale PID, PID reuse, unsafe file type/link count/permissions, explicit apply, concurrent lock acquisition and byte-for-byte journal preservation.

2. **Actual systemd runtime**
   - CI exercises a real systemd system manager with disposable Linux users, units and runtime directories; the unit starts and restarts.
   - CI also starts the actual `scripts/run_arc_signer.mjs` daemon under systemd, with a temporary EVM key and local HTTPS mock Arc RPC. Startup checks the live RPC `eth_chainId`, Registry runtime code hash and enabled issuer mapping. This test performs no RPC transaction broadcast.
   - Positive/negative Unix socket ACL checks are included: the intended supplementary group can connect; an unrelated unprivileged user cannot.

3. **Full two-role signer execution path**
   - New CI smoke test `tests/arc-signer-full-flow-systemd-smoke.sh` runs two actual signer daemon processes under separate systemd users (`issuer` and `agent`) against a stateful local mock RPC.
   - It creates an ephemeral valid Ed25519 Verigate authorization, then executes: issuer `register` → agent `consume` → agent exact ERC-20 USDC `payment`.
   - The mock validates Arc chain ID, zero native value, issuer/agent sender separation, Registry/USDC destinations, selectors, executor binding, same authorization ID and signed-intent hash, and exact payment recipient/amount calldata.
   - Cross-role operations are rejected. Repeating all three completed requests returns journaled results with `replay: true`. The mock accepts exactly three local raw transactions.
   - Log evidence from run #43227346896:
     - register tx hash in mock: `0x9cb0dabcb4427cdf739faca2e2e19e95e17412ccdf355f255a2ed6e32935e423`
     - consume tx hash in mock: `0x7ec96b465042710cffdea9d5f740cb0881d6b50f944029184eebf7efeaa07ecb`
     - payment tx hash in mock: `0x84bec124d29cad32abe60e2cff2b7ef7a10c1228c32f86df33bfc363991de3e1`
   - These are synthetic local mock-RPC transaction hashes, **not Arc Mainnet transactions**. No public RPC or mainnet transaction was used.

4. **Actual RPC chain identity**
   - Fixed an ethers `staticNetwork` blind spot: adapter startup now explicitly calls `provider.send("eth_chainId", [])` and checks the actual RPC response equals 5042, then checks the provider's configured network too.
   - Added a regression test where `getNetwork()` says 5042 but the actual RPC `eth_chainId` says 1; adapter startup must reject.
   - The `contracts` job in run #43227346896 passed `Constrained Arc signer policy tests`, the systemd daemon tests and the full-flow signer test.

### Read-only Arc fee evidence

- Fee accounting units are now explicit: Arc native USDC uses 18 decimals for gas cost; canonical USDC ERC-20 transfers use 6 decimals. `gasUsed × effectiveGasPrice`, `maxNativeCost` and `dailyNativeBudget` are native 18-decimal USDC base units. EVM fee-per-gas settings remain wei/gas. Divide native totals by `10^12` to express the six-decimal ERC-20 equivalent.
- Read-only sampler: `scripts/verify_arc_fee_samples.mjs`; npm command `npm run verify:arc-fee-samples`. It verifies RPC chain ID, transaction destination and selector, receipt success/hash and fee fields. It has a chain-checked Arcscan fallback for pruned historical receipts.
- CI run #43225423264 (before adding the full-flow test) recorded all four samples; the latest run #43227346896 also completed the read-only fee step successfully.
- Verigate Registry historical receipts:
  - Registration #1, tx `0xa6a2fb23af073085c64bb168f14ee02d90d64fbeb4629dc2724ba1d01624867f`, block 30024727, gas 94,914, effective price 25.75 Gwei, fee **0.0024440355 native USDC**.
  - Registration #2, tx `0x5f45d89e0f12e42a0d00268d6125a2b05f6474f4ed786895bc7715cf39ad1696`, block 30025935, gas 94,914, 25 Gwei, fee **0.00237285 native USDC**.
  - Consumption, tx `0xc0b2a5de7973da979808ebf5f69e4736ad1eea22fc1fdd5f698b2b44cbad5de8`, block 30026205, gas 34,267, 25.75 Gwei, fee **0.00088237525 native USDC**.
- Separate-project fee reference only:
  - Guardian v3 ERC-20 USDC transfer, tx `0xd781e8b04b5ca89c3a34fcec50a6636049f7647d2b0e1b2bb64d5b1ee54daadf`, block 21448559, gas 48,722, 21.014 Gwei, fee **0.001023844108 native USDC**. This belongs to Agentic Wallet Guardian v3; it is not a Verigate payment or settlement proof.
- Historical sample max is 0.0024440355 native USDC for registration. It is insufficient to set production limits on its own. No production fee ceilings have been selected or approved. Issuer and agent budgets remain per-instance, not one shared global budget.

### Arc integration evidence boundary

- Arc Mainnet chain ID: 5042.
- Registry: `0x4D09CdD490c1Ce48BCB6DA5c1A6Bf41E2f5e853D`.
- Verified Registry runtime hash: `0x6b229c049b9ba0007c318a10759a9827b5a798a4e511611872dcd4cf3973b160`.
- Deployer/owner: `0x1429906b663608Db6aDeAb8F975B47aFbbe8c68C`.
- Registry deployment evidence and historical read-only checks are recorded in PR #56 and [run #43160472757](https://github.com/rudimentall1/verigate/actions/runs/43160472757).
- PR #57 contains mocked API/RPC settlement verification coverage and a wallet hand-off path. No Verigate-authorized Arc Mainnet USDC payment is claimed. No live settlement transaction hash exists for this Verigate flow.
- The full signer flow proven by #43227346896 uses ephemeral keys and a local synthetic mock RPC; it proves code-path orchestration, role boundaries, exact calldata and idempotency, not live Arc behavior.

### Deployment and operational boundaries

- No production key provisioning or copying occurred.
- No signer daemon was installed or started on Gensyn2.
- No live signer transaction was broadcast.
- No Gensyn2 access was performed during this work. FLOP, AegisForge, OWNERA and unrelated services remain untouched.
- Actual target-host UID/group mapping, runtime directories, RPC availability, fee configuration and rollback readiness still require a separately approved read-only inventory and operator review.
- This remains OS-isolated signing, not an HSM and not protection against root/host compromise.

### Next actions

1. Wait for and inspect the final `anna-ui` result in run #43227346896. Confirm exact current PR #58 head and ensure the latest code commit remains fully green.
2. If CI passes, conduct a focused adversarial review of the full-flow mock: malformed signature, expired authorization, altered recipient/amount, wrong signer, pending/broadcast crash windows and nonce contention. Add only gaps not already covered by unit tests.
3. Finish a separate fee review after a real Verigate USDC payment receipt exists; do not substitute the Guardian reference for Verigate settlement. Do not set production max-fee or daily-budget values until reviewed.
4. Only after code/CI review and explicit approval, inventory Gensyn2 read-only and identify the real issuer/agent client service accounts. Do not install or start the signer in that step.
5. Keep PR #57 and #58 Draft/Open until their integration boundary, release plan and live evidence are reviewed. No merge, production key provisioning or mainnet broadcast without separate explicit approval.


## 26. Arc signer orchestrator split — 2026-11-12

This section updates the deployment architecture described in section 25. The prior single-process convenience wrapper is retained only for a trusted coordinator; production roles are now exposed as separate application phases.

### Problem found

- The first signer-client orchestration entrypoint accepted both `issuerSignerClient` and `agentSignerClient`.
- A process using it therefore needed permission to access both Unix sockets. That contradicted the deployment trust boundary: the autonomous agent runtime must not be able to access the operator-controlled issuer socket.
- This was an architecture/deployment mismatch, not a private-key leak. Socket access grants the typed role operation, so it is still a meaningful authority boundary and must remain separated.

### Implemented split

- Added `registerArcAuthorizationWithIssuerSignerClient()`:
  - intended for an operator-controlled issuer controller only;
  - accepts the authorization request, calls Verigate `/authorize`, checks the signed authorization and pinned Registry/issuer/agent, validates independently derived registration calldata;
  - submits `register` using only the issuer socket;
  - calls Verigate `/registration/confirm`;
  - returns the signed authorization and confirmed `registration_tx_hash` as the hand-off to the agent phase.
- Added `executeRegisteredArcPaymentWithAgentSignerClient()`:
  - intended for the agent runtime;
  - accepts only the authorization and operator-confirmed registration transaction hash;
  - re-confirms registration through Verigate before any agent signer request;
  - validates independently derived consume calldata, consumes with the agent socket, confirms consume, validates exact USDC payment calldata, pays with the agent socket and confirms settlement;
  - requires no issuer signer client or issuer socket access.
- Retained `executeAuthorizedArcPaymentWithSignerClients()` as a backward-compatible trusted-coordinator wrapper. Its code comment and docs explicitly prohibit using it inside the autonomous agent runtime because it requires both socket permissions.
- Updated `docs/ARC_AGENT_SIGNER_SERVICE.md` to prescribe separate operator and agent controller processes.

### Tests and CI

- Added split-phase tests in `tests/arc-agent-executor.test.mjs`:
  - separate issuer and agent phases execute the confirmation sequence;
  - agent phase re-checks operator registration and refuses to consume if Verigate no longer confirms it;
  - issuer phase requires only an issuer signer client;
  - agent phase receives only the agent signer client.
- The new tests passed in CI run [#43228511154](https://github.com/rudimentall1/verigate/actions/runs/43228511154):
  - `Headless Arc agent executor workflow tests`: PASS, including tests 18–20 for split roles;
  - `Constrained Arc signer policy tests`: PASS;
  - real systemd runtime test: PASS;
  - actual signer daemon mock-RPC startup/restart test: PASS;
  - full issuer → agent register/consume/payment local mock flow: PASS;
  - `test` and `container`: PASS.
  - `anna-ui` was still running at the time of this update. Do not report this run as 4/4 until it completes.
- Latest signer branch head at this checkpoint: `b4567fe08bc3746aef339d858568edf7f6125b47`. PR #58 remains Draft/Open, stacked on PR #57, not merged.

### Current role deployment rule

- Operator controller: may access the issuer socket only; runs `registerArcAuthorizationWithIssuerSignerClient`.
- Agent runtime: may access the agent socket only; receives the signed authorization and registration transaction hash; runs `executeRegisteredArcPaymentWithAgentSignerClient`.
- Neither process receives either private key. The OS user/group mapping must enforce the boundary; application code alone is insufficient.
- Do not deploy the backward-compatible two-client wrapper as the agent runtime entrypoint.

### Immediate next gate

- Wait for the remaining Anna UI job in run #43228511154 and capture the final 4/4 result.
- Then review the role-to-systemd-user configuration and target host account mapping in a separately approved read-only inventory. Do not install or start signers on Gensyn2 at this stage.


## 27. Cross-role Unix socket ACL regression — 2026-11-13

### Finding

The full systemd mock-RPC test already created distinct service users and client users, and verified each client could use its own role socket. It did not explicitly assert the inverse boundary: issuer client must not connect to agent socket, and agent client must not connect to issuer socket. The service unit and runtime-directory permissions were designed to enforce this, but the exact cross-role denial was not directly tested.

### Change

- Updated `tests/arc-signer-full-flow-systemd-smoke.sh` so `assert_denied` accepts an explicit caller identity.
- The test now checks:
  - unrelated user denied from issuer socket;
  - unrelated user denied from agent socket;
  - issuer client denied from agent socket;
  - agent client denied from issuer socket.
- Existing positive checks remain: issuer client uses issuer socket; agent client uses agent socket.
- The test continues to run the actual two signer daemons under separate systemd users against local HTTPS mock RPC. It performs only synthetic local broadcasts, never a public Arc transaction.

### CI status

- Change commit: `6c54460e627b4c3b40a60fc187528e57aff2edbc`.
- CI run [#43364690275](https://github.com/rudimentall1/verigate/actions/runs/43364690275) was **in progress** when this checkpoint was written. Do not claim the new cross-role ACL assertions passed until the `contracts` job completes successfully.
- PR #58 remains Draft/Open, stacked on PR #57. No merge, Gensyn2 access, production key provisioning or live signer broadcast.

### Next

1. Inspect run #43364690275, especially the full-flow systemd test. If cross-role denial fails, fix the group/directory ACL model rather than weakening the test.
2. If CI passes 4/4, update PR #58 evidence and this checkpoint with the exact successful run.
3. Continue adversarial review of handoff integrity, duplicate authorization, concurrent signer requests and ambiguous RPC outcomes. Do not install on Gensyn2 until code review is complete and a separate read-only inventory is explicitly approved.


## 28. CI regression found while adding cross-role ACL checks — 2026-11-13

### CI failure diagnosis

- Run [#43364690275](https://github.com/rudimentall1/verigate/actions/runs/43364690275) failed in the existing `journal enforces cumulative daily native-token budget` unit test before the new systemd cross-role ACL smoke test ran.
- Root cause was a brittle test clock, not a budget implementation regression: the test reserved against hard-coded UTC date 2026-11-12, while `OperationJournal.complete()` stamped settlement using the real current date (2026-11-13). The completed reservation therefore correctly fell outside the test's artificial day, and the test's expected budget exception did not occur.
- Fixed determinism by allowing `OperationJournal.complete(..., authorizationKey, now)` to accept an optional timestamp (production default remains `Date.now()`), and changed the budget test to complete against its injected test day.
- This does not alter production settlement accounting: completed operations continue to count against their actual settlement UTC day. Unresolved reservations remain charged against new-day budgets until reconciled.

### Current code commits

- Cross-role ACL assertions: `6c54460e627b4c3b40a60fc187528e57aff2edbc`.
- Deterministic journal settlement timestamp: `200f71c001b035aee1472b9c6893477810924be4`.
- Deterministic budget test: `a571fcf1a399b0bf925e91917eb361e308c91dbd`.
- A fresh CI run for the latest head is required. Do not treat failed run #43364690275 as validation of the new cross-role assertions.


## 29. Cross-role ACL and deterministic budget tests — verified — 2026-11-13

This section supersedes the pending CI status in sections 27–28.

### CI result

- CI run [#43364796152](https://github.com/rudimentall1/verigate/actions/runs/43364796152) completed **4/4 PASS**: `contracts`, `test`, `container`, `anna-ui`.
- Tested implementation commit: `a571fcf1a399b0bf925e91917eb361e308c91dbd`.
- Latest branch/PR #58 head at checkpoint update: `e52c8557dcc21b42eb166a3b4763643d7b4fdd81`; this adds checkpoint documentation after the tested code. PR #58 remains Draft/Open and stacked on PR #57.

### Security boundary now covered in CI

The `contracts` job's full systemd mock-RPC flow passed with these explicit OS-level access checks:

- issuer client can connect to issuer signer socket;
- agent client can connect to agent signer socket;
- issuer client is denied access to agent signer socket;
- agent client is denied access to issuer signer socket;
- unrelated user is denied access to both sockets.

The same test then ran the actual issuer and agent signer daemons under distinct systemd users against local HTTPS mock RPC, completed `register → consume → payment`, and verified completed retries replay journal results. Exactly three local raw transactions were accepted. These are synthetic local mock-RPC transactions, not Arc Mainnet transactions.

### Budget test clock fix

- Run #43364690275 exposed a test-only mismatch between a fixed 2026-11-12 budget day and `complete()` using the real 2026-11-13 settlement day.
- `OperationJournal.complete()` now accepts an optional injected timestamp for deterministic tests; its production default remains `Date.now()`.
- The daily-budget test now completes the reservation on its injected test day. Production accounting still records the actual settlement UTC day, and unresolved reservations remain charged against later-day limits until reconciled.
- The corrected test passed in #43364796152.

### PR state and evidence boundary

- PR #58 description updated with the successful 4/4 run and cross-role socket ACL evidence.
- PR #58 remains Draft/Open; PR #57 remains separate and unmerged.
- No Gensyn2 access or changes, no production key provisioning, no signer service installation, and no live Arc signer transaction.
- This remains OS-isolated constrained signing, not HSM/KMS isolation and not protection against host-root compromise.

### Next engineering work

1. Continue a targeted adversarial review of the API-to-signer handoff: signed authorization integrity, registration hash confirmation, altered handoff data, expired authorization at each boundary, and duplicate/concurrent requests.
2. Review journal reconciliation after ambiguous RPC outcomes; the service intentionally fails closed and does not auto-rebroadcast. Define a safe operator procedure for resolving `reserved` and `broadcast` records.
3. Review per-role daily budget limitations and production fee policy only after a real Verigate-authorized Arc USDC payment receipt exists. Do not use synthetic mock receipts as fee evidence.
4. Only after this code review and separate explicit approval, perform read-only Gensyn2 account/group/process inventory. Do not provision keys or install/start units without a further explicit decision.


## 30. Registration handoff tamper regression — 2026-11-13

### New test

- The agent-side orchestration receives a signed authorization plus the issuer registration transaction hash. The authorization signature protects the authorization payload; Verigate's registration-confirm endpoint must independently confirm the supplied transaction hash before the agent signer is called.
- Strengthened the test API fixture so `/registration/confirm` returns `registered: true` only for the expected issuer transaction hash.
- Added a regression test that substitutes a different valid-format bytes32 registration hash. The agent phase forwards that hash for independent confirmation, receives `registered: false`, and refuses to call either `consume()` or `payment()`.
- Test file: `tests/arc-agent-executor.test.mjs`.

### CI

- Implementation/test commit: `8b81df4d45a5ceacfd1a41083ceef96b24551c80`.
- CI run [#43365056806](https://github.com/rudimentall1/verigate/actions/runs/43365056806) is running. At checkpoint update, `contracts`, `test`, and `container` are successful; `anna-ui` is still running. The `Headless Arc agent executor workflow tests` step passed, including the new handoff-hash test. Do not claim this run is 4/4 until `anna-ui` finishes.
- Latest PR #58 head: `8b81df4d45a5ceacfd1a41083ceef96b24551c80`. PR #58 remains Draft/Open and stacked on PR #57.

### Next

1. Confirm run #43365056806 reaches 4/4.
2. If green, update the PR description and checkpoint with the exact final run result.
3. Continue with operator reconciliation for ambiguous `reserved`/`broadcast` journal states. Do not auto-rebroadcast or erase records.
4. No Gensyn2 inventory or changes, production key provisioning, service installation, or live signer broadcast without separate explicit approval.


## 31. Arc signer CI completion and read-only journal reconciliation — 2026-11-13

### CI completion for the previous implementation slice

- CI run [#43365056806](https://github.com/rudimentall1/verigate/actions/runs/43365056806) completed **4/4 PASS**: `contracts`, `test`, `container`, `anna-ui`.
- Tested implementation commit: `8b81df4d45a5ceacfd1a41083ceef96b24551c80`.
- The run includes the handoff-tampering regression: an altered issuer registration transaction hash is rejected by Verigate registration confirmation before either agent `consume()` or `payment()` signer method is invoked.
- The run does not test a live Arc signer transaction. The full signer flow remains local mock-RPC evidence only.

### New read-only journal inspection

- Added `scripts/inspect_arc_signer_journal.mjs` and npm command `npm run inspect:arc-signer-journal -- /absolute/path/to/operations.jsonl`.
- The CLI reads the existing append-only journal through `OperationJournal.records()`, inheriting its regular-file, owner, link-count and permission checks.
- It groups operation events by authorization key and operation, validates allowed state transitions, and reports the latest `reserved`, `broadcast` or `complete` state.
- Exit code 3 indicates one or more unresolved operations; exit code 1 means inspection was refused or the journal is malformed.
- Added tests proving the inspector:
  - reports reserved-without-hash as ambiguous, not as proof that no broadcast occurred;
  - reports broadcast transaction hashes for exact receipt inspection;
  - preserves journal bytes;
  - refuses invalid state transitions.
- Added the new tests and syntax check to `test:arc-constrained-signer`.

### Operator reconciliation policy

- Updated `deploy/arc-signer/LOCK-RECOVERY.md` and `docs/ARC_AGENT_SIGNER_SERVICE.md`.
- `broadcast`: inspect the exact hash and verify chain ID, signer, nonce, destination, calldata, value, receipt status, block/finality and actual fee against the derived operation.
- `reserved`: no durable hash is present, but broadcast may have happened before the crash. Inspect signer nonce, pending pool, account history and independent RPC evidence. A missing hash or a single RPC miss is not proof of no broadcast.
- Pending, pruned, reverted, inconsistent or otherwise ambiguous outcomes remain blocked. Never auto-rebroadcast, clear the journal, issue a replacement authorization to bypass the block, or manually edit journal records.
- The inspector is deliberately read-only. It does not query RPC, append terminal records, change budgets, resolve operations or authorize a retry. Any future state-transition tool requires separate security review and explicit operator approval.

### Current branch / CI status

- New inspector implementation, tests, package wiring and runbook changes are on `feat/arc-agent-signer-service-2026-11-12`.
- Latest code/docs branch head at checkpoint time: `f12a32fc5a6acff16609623413325448aa0732f1`.
- The previous exact implementation head `8b81df4d...` passed run #43365056806 4/4. The new journal-inspector changes are **not yet CI-verified**; wait for a fresh run on the new head before calling them tested.
- PR #58 remains Draft/Open and stacked on PR #57. Do not merge or change Draft state without explicit approval.

### Safety boundary unchanged

- No Gensyn2 access or changes.
- No production keys provisioned.
- No signer service installed or started on Gensyn2.
- No live Arc signer transaction broadcast.
- FLOP, AegisForge, OWNERA and unrelated services remain untouched.


## 32. Journal inspector hardening and CI run — 2026-11-13

### Additional fail-safe correction

- The read-only inspector now refuses a missing journal path rather than reporting a zero-record empty journal. A typo or wrong mount path must not be mistaken for a clean journal.
- Added a regression test for this behavior.
- Latest implementation/test head: `fe2547cd88338cd2b22fc7bd8cdac8d868117ebe`.

### CI

- PR CI run [#43366379519](https://github.com/rudimentall1/verigate/actions/runs/43366379519) completed **4/4 PASS** (`contracts`, `test`, `container`, `anna-ui`) for implementation/test head `fe2547cd88338cd2b22fc7bd8cdac8d868117ebe`.
- The `contracts` job passed the constrained signer policy tests (including inspector tests), real systemd runtime smoke, daemon mock-RPC smoke and full two-role local mock-RPC flow. `test`, `container` and `anna-ui` also passed.
- Workflow run head SHA is `fe2547cd...`; PR head at completion is `9888b5df855c2a09f970feffe028c03dfc29c0be` due to checkpoint-only documentation commit.

### Current state

- PR #58 remains Draft/Open, stacked on PR #57.
- The inspector remains read-only: it does not query RPC, append operation outcomes, alter budgets, clear replay protection or authorize rebroadcast.
- Gensyn2 remains untouched. No keys provisioned, no signer installed or started, and no live Arc signer transaction broadcast.


## 33. Journal inspector CI green; next release gate is fee evidence — 2026-11-13

### Verified state

- CI run [#43366379519](https://github.com/rudimentall1/verigate/actions/runs/43366379519) completed **4/4 PASS** for the implementation/test head `fe2547cd88338cd2b22fc7bd8cdac8d868117ebe`.
- Jobs: `contracts`, `test`, `container`, `anna-ui`.
- The constrained signer policy test step passed, including read-only journal inspector tests for unresolved states, invalid transitions, no mutation and missing-file refusal.
- Systemd runtime smoke, daemon mock-RPC smoke and full two-role local mock-RPC flow passed in the contracts job.
- PR #58 remains Draft/Open and stacked on PR #57. Current PR head at checkpoint time: `9888b5df855c2a09f970feffe028c03dfc29c0be`; the later commit is checkpoint documentation only.
- No live Arc signer transaction was broadcast. Mock-RPC evidence remains synthetic/local.

### Lock recovery review

- Existing stale-lock recovery is inspect-first and requires explicit `--apply`.
- Lock metadata records PID, Linux boot ID and process start ticks; inspection checks owner, permissions, link count, inode identity and process identity.
- Tests cover live owner refusal, PID reuse, explicit stale recovery, malformed metadata, symlink/hard-link/broad-mode refusal and preservation of journal bytes.
- Recovery never changes operation records or resolves a transaction reservation.
- Operational precondition remains: stop the affected signer instance and verify no process is using its journal before explicit stale-lock recovery. Root/host compromise is outside this OS-isolation model.

### Next engineering gate: fee evidence, not more features

- Inspect the read-only fee sampler and verify that every sample is bound to Arc chain 5042, exact tx hash, expected sender/destination, selector, receipt block and successful status.
- Separate evidence classes: Verigate Registry register/consume receipts versus the Guardian ERC-20 transfer reference. Do not treat the latter as a Verigate payment sample.
- Production payment fee ceiling cannot be approved without a real Verigate-controlled USDC payment receipt. Existing historical samples are informative only.
- Do not invent fee limits, set production budgets, provision keys, deploy or start services. Keep Gensyn2 untouched until separately approved.


## 34. Arc fee evidence review and production dependency correction — 2026-11-13

### Historical receipt evidence read from CI

- Run [#43366379519](https://github.com/rudimentall1/verigate/actions/runs/43366379519) executed `npm run verify:arc-fee-samples` successfully against Arc Mainnet read-only RPC.
- Verigate Registry registration receipt 1: tx `0xa6a2fb23af073085c64bb168f14ee02d90d64fbeb4629dc2724ba1d01624867f`, block 30024727, gasUsed 94914, effectiveGasPrice 25.75 gwei, fee `0.0024440355` native USDC.
- Verigate Registry registration receipt 2: tx `0x5f45d89e0f12e42a0d00268d6125a2b05f6474f4ed786895bc7715cf39ad1696`, block 30025935, gasUsed 94914, effectiveGasPrice 25 gwei, fee `0.00237285` native USDC.
- Verigate Registry consumption receipt: tx `0xc0b2a5de7973da979808ebf5f69e4736ad1eea22fc1fdd5f698b2b44cbad5de8`, block 30026205, gasUsed 34267, effectiveGasPrice 25.75 gwei, fee `0.00088237525` native USDC.
- Separate Agentic Wallet Guardian v3 ERC-20 transfer reference: tx `0xd781e8b04b5ca89c3a34fcec50a6636049f7647d2b0e1b2bb64d5b1ee54daadf`, block 21448559, fee `0.001023844108` native USDC. This is explicitly not Verigate payment evidence.
- The full-flow systemd smoke produced a local mock payment cost of `0.0012545915` native USDC. It is synthetic mock-RPC evidence and must not be treated as a real receipt.
- Conclusion: there is still no independently verified live Verigate-controlled Arc USDC payment receipt. Do not set production payment fee ceiling or daily budget from the unrelated transfer reference or mock-RPC output.

### Production dependency defect found and corrected in source

- `integrations/arc-ethers-signer-adapter.mjs` imports `ethers` at runtime, but `package.json` previously declared ethers only under `devDependencies`. A production install using `npm ci --omit=dev` would therefore omit a required runtime package.
- Moved `ethers: ^6.17.0` to production `dependencies`, removed it from `devDependencies`, and updated the lockfile production dependency graph (ethers plus eight transitive packages).
- Added CI step `Verify Arc signer production-only installation`: run `npm ci --omit=dev --ignore-scripts` and import `integrations/arc-ethers-signer-adapter.mjs`.
- Updated deployment docs to require `npm ci --omit=dev` for the signer runtime.
- Implementation/CI workflow head: `b8ac89d69cb94f8c3a1b543302fb1201b18b82e9`. CI run [#43367601961](https://github.com/rudimentall1/verigate/actions/runs/43367601961): `contracts`, `test` and `container` have passed; `anna-ui` is still running. Crucially, the `Verify Arc signer production-only installation` step completed **PASS**, confirming `npm ci --omit=dev --ignore-scripts` and runtime import of the signer adapter.
- A later documentation-only commit updated deployment instructions. Current PR head at checkpoint time: `f32e9c08285e07669db452b1008bac18b468d9da`.

### Dependency security note

- The preceding `npm ci` in CI reported 36 audit findings: 1 low, 5 moderate, 25 high and 5 critical. No blanket `npm audit fix --force` was applied. Before release, inspect the exact advisories and dependency paths, distinguish dev-only tooling from production runtime exposure, and update only with compatibility tests.
- The production-only install check is intended to prove runtime packaging, not to certify the full dependency tree as vulnerability-free.

### Release state

- PR #58 remains Draft/Open and stacked on PR #57.
- No live Arc signer payment has been broadcast.
- No production keys, service accounts, or target-host deployment have been provisioned.
- Gensyn2 and unrelated services remain untouched.


## 35. Arc signer CI green; receipt binding and dependency audit diagnostics — 2026-11-13

### Completed CI run

- CI run [#43367601961](https://github.com/rudimentall1/verigate/actions/runs/43367601961) completed **4/4 PASS**: `contracts`, `test`, `container`, `anna-ui`.
- The production-only dependency check passed: `npm ci --omit=dev --ignore-scripts` followed by importing `integrations/arc-ethers-signer-adapter.mjs`.
- The run validates workflow head `b8ac89d69cb94f8c3a1b543302fb1201b18b82e9`; it does not validate later fee-sampler/audit-diagnostic edits.
- PR #58 remains Draft/Open and stacked on PR #57.

### Dependency audit numbers

- Full install reported 36 findings: 1 low, 5 moderate, 25 high, 5 critical.
- Production-only install reported 27 findings: 1 low, 5 moderate, 17 high, 4 critical.
- These are counts only; exact advisories and dependency paths have not yet been reviewed. Do not treat the production-only runtime import check as a vulnerability clearance.
- Added a CI diagnostic step to print full and production-only npm audit advisory names, severity, directness, affected range, and fix availability. Await a fresh CI run for exact results. No blanket `npm audit fix --force`.

### Fee sampler audit and correction

- Review found the previous sampler checked transaction destination and selector plus receipt hash/status, but did not pin expected sender, verify the transaction's own chain ID, compare receipt sender/destination to the transaction, require zero native value, or bind transaction inclusion block/hash to the receipt.
- Hardened `scripts/verify_arc_fee_samples.mjs` with those checks. Expected sender is now explicit for each historical sample; Registry samples use the configured issuer address, while the separate Guardian transfer remains clearly marked as reference-only.
- Added no claim that these are Verigate payment receipts. There is still no live Verigate-controlled Arc USDC payment receipt, so production payment fee ceilings and daily budgets remain blocked.
- CI must pass on the hardened sampler before its stronger checks are considered verified.

### Latest branch changes awaiting CI

- `dd98f6636d7343070f5ebf0f6c7929d989699a2c`: fee sampler receipt-binding hardening.
- `b81c05d88a3fdd2c45b9153e405668e8887f81b9`: CI diagnostic output for full and production npm audit advisories.
- Current PR head: `b81c05d88a3fdd2c45b9153e405668e8887f81b9`.
- Do not claim the fee-sampler hardening or audit diagnostic has passed until a fresh CI run completes.

### Safety boundary

- PR #58 stays Draft/Open; do not merge PR #57 or #58 without explicit approval.
- No Gensyn2 access or changes; no production keys, signer install/start, or live signer transaction.
- FLOP, AegisForge, OWNERA and unrelated services remain untouched.
