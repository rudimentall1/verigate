# Verigate Session Checkpoint

**Updated:** 2026-11-12 10:55 +05:00
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


## 20. Arc USDC payment settlement confirmation — implementation PR #57

### Why this slice was added

The existing Arc flow stopped after Verigate confirmed Registry registration and one-time consumption and returned the exact USDC wallet transaction. The wallet broadcast was separate and explicit, but there was no dedicated API endpoint to verify that the payment itself settled.

### Implementation branch and PR

- Branch: `feat/arc-payment-settlement-confirmation-2026-11-12`
- Draft PR #57: https://github.com/rudimentall1/verigate/pull/57
- Current head: `32b7fa82aabca002ab3f8358ef4cf755b9f1ba0a`
- Base: `main`
- State: open, Draft, mergeable, unmerged.
- 9 changed files. The PR has multiple incremental commits from the connector-based editing workflow; merge as a squash commit if eventually approved. Do not merge without explicit authorization.

### New API

`POST /v1/integrations/arc/payment/confirm`

The endpoint accepts the original signed Execution Authorization and the registration, consumption and payment transaction hashes. It re-verifies the signed authorization and Registry registration/consumption before checking the payment.

The payment verifier checks:
- Arc chain ID 5042.
- Signed sender, canonical Arc USDC token destination, zero native value and exact transfer calldata.
- Payment transaction hash and transaction/receipt block number, block hash and transaction index agreement.
- Successful payment receipt.
- Exactly one `Transfer(address,address,uint256)` event emitted by canonical USDC, matching signed sender, recipient and exact base-unit amount.
- Payment ordering after Registry consumption, including transaction index when both are in the same block.
- Canonical inclusion block hash and inclusion at or below Arc's finalized head.
- Successful consumption receipt and matching transaction/receipt inclusion coordinates.

The endpoint returns `settled=true` and structured settlement evidence only after all checks pass. RPC availability failures return 503; invalid or mismatched evidence returns 409. The endpoint does not broadcast transactions or custody wallet keys.

### Wallet client

Added `confirmArcPayment` to `integrations/arc-client.mjs`. It waits for the wallet-broadcast payment receipt, submits the original authorization and all three transaction hashes, then requires `settled=true` and `payment_settlement.verified=true`.

Updated:
- `docs/arc-mainnet-integration.md`
- `docs/ARC_WALLET_CLIENT.md`
- `docs/evidence/arc-mainnet.md`

The evidence document explicitly labels this as source implementation under CI review, not a live payment.

### Tests and CI

Latest PR CI run: [43162858818](https://github.com/rudimentall1/verigate/actions/runs/43162858818).

At last inspection:
- Full Python test suite: **PASS**, 669 tests.
- Contract tooling and Arc wallet client tests: **PASS**.
- Container build/auth smoke: **PASS**.
- Anna UI E2E: still in progress; Linux Executa build/smoke has not yet run in this attempt.

Earlier intermediate CI attempts had one test assertion failure because the negative-order test changed the receipt index but not the corresponding transaction index. The test fixture was corrected to keep transaction/receipt coordinates consistent before asserting the ordering rule. The latest full Python test suite passes.

### Evidence boundary

- This endpoint is source code on an unmerged Draft PR.
- No live Verigate-authorized Arc USDC payment has been broadcast or verified.
- No hosted Verigate API deployment or Gensyn2 server change.
- No Registry owner/issuer mutation, contract deployment or transaction broadcast.
- PR #57 must remain unmerged until complete CI and review pass, followed by a separate explicit deployment decision.
