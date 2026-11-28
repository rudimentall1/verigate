# Verigate — Current Working Checkpoint

**Updated:** 2026-11-28  
**Repository:** https://github.com/rudimentall1/verigate  
**Purpose:** current engineering handoff and next verifiable work. This file supersedes neither release evidence nor the product/security specifications; those remain in their owning documents.

## Product direction

Verigate is an Agent Authority Control Plane: an agent proposes an exact consequential action; Verigate evaluates authority; the execution boundary enforces the authorization; evidence makes the result independently verifiable.

The recent TheDAO Security Fund rejection is a product-readiness signal, not a reason to add more infrastructure. The fund's two concrete objections were:
- $60k of the $90k request was for building Ethereum-native components from scratch (authorization profile, conformance suite, SDK), rather than extending a working Ethereum base.
- It could not identify independent teams using Verigate; the only external application it found was one test transfer on Base.

**Strategic rule:** no new SDK/profile/conformance layer is the next milestone. The next adoption milestone is one independent external agent/application integration that repeatedly uses Verigate and demonstrates both an authorized action being executed and an unauthorized/mutated action being blocked before side effects. Internal Anna demos and self-authored tests are not independent adoption.

## Current repository facts checked on 2026-11-24

- Default branch `main` was at `634cd6f8f60953cbfdcacf2388cfb4fd3692aeb1` (2026-11-21).
- PR [#80 — keep wallet governance reconciliation database read-only](https://github.com/rudimentall1/verigate/pull/80) is **open and Draft**.
- PR #80 head: `fix/wallet-governance-reconcile-readonly-db`, latest SHA `dae7604ea16f8fd25541853c3ab28b3219cedf51`.
- PR #80 base: `docs/wallet-governance-integration-acceptance`, SHA `e21d3771533f1774d42094f808dd986f61bd3cea` (the head of PR #79).
- PR #80 is 4 commits ahead of its declared base and changes only three files:
  - `docs/wallet-governance-log-reconciliation.md`
  - `scripts/wallet_governance_log_reconcile.py`
  - `tests/test_wallet_governance_reconcile_readonly.py`
- Latest-head GitHub Actions CI passed all four jobs: [run 45331764542](https://github.com/rudimentall1/verigate/actions/runs/45331764542).
  - Full Python suite: **761 tests, OK**.
  - Anna UI E2E: **69/69 passed**.
  - Contracts job: passed.
  - Container build and API-auth smoke: passed.
  - Linux Anna Executa 0.1.18 binary smoke: passed, including signed ALLOW, one-time App approval, one-time wallet hand-off and persisted/verified receipt.
- During review, I found that the original write-rejection test opened a *separate* read-only connection; it did not prove that the loader's own connection rejected writes. Replaced it with a probe against the actual connection created by the loader. This is in commit `dae7604...`; the full CI run above passed with the corrected test.
- No local tests were run in this review session; the results above are GitHub Actions evidence for the exact head SHA.
- The implementation reads SQLite via URI `mode=ro`, enables `PRAGMA query_only = ON`, and closes the connection. Focused tests cover a missing DB path, unchanged schema/row count, and a write attempt against the loader's actual connection.
- PR [#81 — current working checkpoint](https://github.com/rudimentall1/verigate/pull/81) is open and Draft, based on `main`; it adds this file and records the current plan.
- The reconciliation acceptance document requires disposable databases, synthetic principals/keys/tokens, independent checkpoint pins, and no production credentials or live funds. Scenarios A–J are a procedure, not evidence that an end-to-end acceptance run has passed.

## Stacked PR lineage — important

PR #80 is **not an isolated branch that should be retargeted to main**. It is the final PR in a stacked sequence:
- #70: non-finite governance timestamps
- #71: historical wallet enrollment verification
- #72: wallet governance in portable proofs
- #73: external transparency log
- #74: transactional outbox
- #75: authenticated HTTP transport
- #76: overlapping bearer-token rotation
- #77: outbox health monitoring
- #78: local/remote log reconciliation
- #79: integration acceptance plan
- #80: read-only reconciliation DB access

Each PR from #71 through #80 targets the head branch of the preceding PR; #80 targets #79. All inspected PRs #70–#80 remain open and Draft, and GitHub reports their latest heads as mergeable. CI for each inspected head has a successful run: #70–#79 runs `44882167775`, `44887470590`, `44890053524`, `44892539675`, `44893461101`, `44894323495`, `44896775114`, `44896858171`, `44897875508`, and `44899187917`; PR #80's latest run is `45331764542`. Mergeability and green CI are not approval or proof of production acceptance.

**Integration rule:** review and land the stack in dependency order, or keep it stacked until the earlier PRs are ready. Do not retarget #80 to main or cherry-pick only its commits; the reconciliation modules it depends on are introduced by earlier stack branches. The full stack's production readiness and end-to-end acceptance still need separate review.

## Immediate engineering work

1. **Finish the PR #80 review.** Inspect the complete four-commit history and relevant surrounding storage/schema code. Check failure behavior for corrupt DBs, missing tables, malformed JSON, URI-special characters in paths, and file permissions. Keep the loader read-only; do not reintroduce `Storage(...)` if its constructor can create/migrate a database.
2. **Review the upstream stack in dependency order.** Start with #70–#79 and establish which PRs are sufficiently reviewed and tested. Do not mark the stack ready based only on PR mergeability or CI.
3. **Run the isolated A–J acceptance procedure.** Use disposable SQLite DBs, synthetic principals, disposable Ed25519 keys and synthetic bearer tokens. Capture sanitized output and commit SHAs. Do not use production credentials, wallet secrets or real funds. A green unit/CI suite alone is not acceptance evidence.
4. **Verify locally from a clean checkout when a connected local runtime is available.** The remote CI suite passed, but local execution remains unperformed; do not represent CI as a local run.

## Product/adoption work — the milestone that matters

After the existing integration path is verified, stop expanding the wallet-governance infrastructure and secure an external integration:
- identify one external agent/application team with an actual consequential action use case;
- get the team to integrate the existing API/SDK path without relying on Verigate maintainers to operate the demo;
- capture repeated runs with exact action, policy, authorization and execution receipts;
- prove one valid action reaches the intended side effect and one unauthorized or tampered action is rejected before the side effect;
- obtain permission to publish the integration and evidence, including the external team's identity and what they built.

**Adoption exit criterion:** at least one independently maintained integration with repeatable, inspectable evidence of both ALLOW and BLOCK at the execution boundary. Do not describe a self-run demo, a single test transfer, a fork with no execution, or an internal Anna flow as independent adoption.

Only after this evidence exists should the grant narrative and budget be rebuilt around deployment, integration support, independent validation and adoption—not foundational SDK/profile construction.

## Safety and reporting rules

- Do not claim local tests passed unless actually run.
- Do not claim the isolated A–J acceptance run passed until evidence exists for every applicable scenario.
- Do not claim independent adoption until an external team has integrated and repeated the flow.
- Do not deploy, provision production keys, rotate live credentials, or send live transactions as part of this work without explicit authorization.
- Keep changes small and reviewable. Update this checkpoint only when repository state, verified evidence, or next action materially changes.

## Next action

Review the stacked PR chain in dependency order and validate the isolated A–J acceptance flow. In parallel, identify the first external integration candidate; do not start another infrastructure feature as a substitute for that adoption work.

## Independent review update — 2026-11-24

A first source-level review of the upstream stack identified two required hardening gaps in PR #70:

1. **Policy deserialization bypasses the new integer-type validation.** GovernancePolicy.from_dict() converts version, threshold, required_roles counts, and max_approval_lifetime_seconds with int() before validate(). Inputs such as booleans, fractional numbers, or numeric strings can therefore be normalized and accepted. PR #70's new tests instantiate GovernancePolicy directly and do not cover the serialized evidence boundary. Fix by validating raw input types before conversion and add from_dict() regression tests.
2. **Historical attestor replay still has unguarded float conversion.** core/attestor_history.py (introduced by base PR #69) still uses math.isfinite(float(value)) for attestation/action/approval timestamps and attestor expiry. An oversized integer can raise OverflowError; some checks occur before the local quorum-verification exception handler, so malformed persisted governance evidence can escape the fail-closed result path. Reuse a safe finite-number predicate and add a replay regression with an oversized integer.

A formal GitHub REQUEST_CHANGES review could not be submitted because the connected GitHub identity is the PR author; GitHub rejects requesting changes on one's own PR. Findings are recorded here pending implementation.

The PR #78 reconciliation CLI initially used Storage(args.database), whose constructor creates schema and performs in-place migrations. That conflicts with the CLI's read-only contract. The downstream PR #80 introduces a dedicated SQLite mode=ro loader and tests writes against the loader's actual connection, so the final stacked head addresses this intermediate-stack issue. Preserve that read-only design when reviewing or rebasing the stack.

PRs #71–#78 were inspected at diff/source level in this pass. No additional confirmed blocker is recorded for those changes yet; this is not a full approval of the stack. PR #72 and #73 are large changes and still warrant focused review of portable verifier parity, trust-anchor handling, and transparency checkpoint replay before the stack is considered ready.

## Follow-up implementation — PR #82 (2026-11-24)

Created Draft PR [#82 — harden governance policy deserialization and attestor replay](https://github.com/rudimentall1/verigate/pull/82), stacked directly on PR #70. Current head: `3c82afdfcd4bd5055b8941d10505d03eb8c9b90f`.

Changes:
- `GovernancePolicy.from_dict()` now validates raw `version`, `threshold`, `max_approval_lifetime_seconds`, and `required_roles` types before construction. Booleans, fractional numbers, numeric strings, malformed role maps, and malformed member collections are rejected instead of coerced.
- Historical attestor verification reuses the overflow-safe `_finite_number` predicate from governance verification for attestation, registration/rotation expiry, action issue time, and approval issue time. Oversized integer timestamps return invalid-evidence results instead of leaking `OverflowError`.
- Added tests for coercible policy values and historical replay with `10**400` action/approval timestamps.

Validation state at checkpoint update:
- GitHub reports PR #82 open, Draft, and mergeable; base is PR #70's head branch.
- No workflow runs or commit status checks were visible yet for head `3c82af...`; CI is pending/unobserved, not passed.
- No local tests were run in this session. Recheck CI and inspect any failures before claiming verification.

Do not merge #82 independently of #70. Once CI is available, review the resulting code/test diff, then resume deeper #72–#73 trust-anchor and portable-verifier review.

PR #82 CI progress update: GitHub Actions run [45334682643](https://github.com/rudimentall1/verigate/actions/runs/45334682643) is running on head `3c82af...`. The full Python test job, cross-language SDK/Arc client checks, end-to-end demo, API smoke check, container job, and contracts job have completed successfully. Anna UI E2E is still running; the workflow is not yet fully green. Do not treat this partial result as complete CI approval.

## 2026-11-24 — governance timestamp review follow-up

### Review findings

- PR #70: GovernancePolicy.from_dict() uses int() before validation. This silently normalizes booleans and fractional values (for example, true -> 1 and 2.5 -> 2), bypassing the strict integer checks added by PR #70.
- PR #69: core/attestor_history.py calls float(value) before guarding overflow in historical attestation, registry boundary, and governance replay timestamps. Oversized persisted integers can raise OverflowError instead of returning a fail-closed verification result.

### Existing remediation branch

- Confirmed that the repository already has a dedicated stacked Draft PR #82 (fix/governance-deserialization-and-attestor-overflow), based on PR #70. It contains stricter from_dict() shape/type validation, a shared overflow-safe finite-number predicate, and regression tests for oversized historical action/approval timestamps and malformed serialized policy values.
- Avoided keeping duplicate remediation commits in PR #69/#70; restored those parent branches to their intended scopes. PR #69's original core/attestor_history.py file was restored after a temporary cleanup deletion.
- PR #82 head: 3c82afdfcd4bd5055b8941d10505d03eb8c9b90f. Its CI run [45334682643](https://github.com/rudimentall1/verigate/actions/runs/45334682643) completed successfully across all four jobs. Local tests were not run.
- PR #82 now reports mergeable=true after parent branch refresh. Its four CI jobs (test, contracts, container, Anna UI) all passed in run 45334682643. It remains Draft and unmerged.

### Current branch/CI state

- PR #69 latest head: 93416056dbd493c2f03c07da46221822df4a0c9f; CI run [45335722138](https://github.com/rudimentall1/verigate/actions/runs/45335722138): test, contracts and container passed; Anna UI was still running.
- PR #70 latest head: 8efde8dbfee14b83f3741764831d931fc548cf2e; run [45335665166](https://github.com/rudimentall1/verigate/actions/runs/45335665166) had test/container failures because it ran while the parent PR #69 branch temporarily lacked core/attestor_history.py. The file is restored; the newer PR #69 CI has passed test/container/contracts. Retry PR #70 failed jobs after its Anna UI job completes.
- PR #69–#70 remain open Draft. No PR was merged, no production service or credential was touched.

### Review continuation

- Continue with PR #82's merge-base/conflict resolution and confirm its regression tests still apply cleanly to the current #69/#70 stack.
- PR #72 wallet enrollment evidence and portable verification, then PR #73 transparency-log anchoring: initial diff review started, not approved. Inspect trust-anchor semantics, duplicate/ambiguous evidence handling, and independent enforcement of every edge and policy pin.

## 2026-11-24 — portable wallet proof and transparency review

### PR #70 CI retry

- The first rerun of PR #70 still failed test/container because the runner checkout lacked core/attestor_history.py (ModuleNotFoundError); the file is present at the current PR #69 and #70 heads. Failed jobs were rerun again after verifying the file at both heads. Latest retry is in progress; do not treat #70 as green until completion.

### PR #72 confirmed defect and fix

- Review found three unsafe float(value) conversions in core/wallet_enrollment_history.py's portable resolver: request attested_at, governance action issued_at, and approval issued_at. The file already had _finite_timestamp(), which catches OverflowError, but these three call sites bypassed it via math.isfinite(float(value)).
- Replaced those casts with _finite_timestamp() and added regression coverage for positive and negative 10**400 attested_at values. This ensures malformed timestamps return a fail-closed result rather than leaking OverflowError.
- PR #72 latest head: b8b2458d88aeb25df598fa07459fe73e002259b0. CI run [45336553627](https://github.com/rudimentall1/verigate/actions/runs/45336553627) was in progress at checkpoint update. Local tests not run.

### PR #72–#73 security review

- PR #72 standalone CLI and packaged verifier already use a safe _finite_wallet_time() predicate for wallet governance timestamps; the gap was in the shared core portable resolver used by offline verification. The standalone and package copies remain duplicated implementations and should be checked for behavioral parity in future changes.
- PR #73 transparency log verifier validates exact history coverage, sequential entry numbers, entry hash chaining, checkpoint binding, signer fingerprint and Ed25519 signature. When both independent log-key and latest-checkpoint pins are supplied, it enforces both. Without pins it explicitly reports the checkpoint as unpinned; docs explain that a signed checkpoint alone is not an independent trust anchor.
- No additional confirmed blocking defect found in the inspected PR #73 log validation path. PR #73 currently reports mergeable=true; this is not approval.
- PR #72 and #73 remain Draft. No merges or production actions performed.

## 2026-11-24 — CI reconciliation and stacked-branch drift

### Refreshed CI state

- PR #69 head `93416056dbd493c2f03c07da46221822df4a0c9f`: CI run [45335722138](https://github.com/rudimentall1/verigate/actions/runs/45335722138) completed successfully; all four jobs passed.
- PR #70 head `8efde8dbfee14b83f3741764831d931fc548cf2e`: CI run [45335665166](https://github.com/rudimentall1/verigate/actions/runs/45335665166) completed with failures in `test` and `container`; `contracts` and `anna-ui` passed.
- PR #72 head `b8b2458d88aeb25df598fa07459fe73e002259b0`: CI run [45336553627](https://github.com/rudimentall1/verigate/actions/runs/45336553627) completed successfully; all four jobs passed.
- PR #73 head `81d52d49a87d0f52c2b114b3a825e13f343c342f`: CI run [44892539675](https://github.com/rudimentall1/verigate/actions/runs/44892539675) completed successfully; all four jobs passed.
- PR #82 head `3c82afdfcd4bd5055b8941d10505d03eb8c9b90f`: CI run [45334682643](https://github.com/rudimentall1/verigate/actions/runs/45334682643) completed successfully; all four jobs passed.
- PR #81 checkpoint head `6bd97769b6ddc7d46edc30569b2fc715060d8882`: CI run [45336712138](https://github.com/rudimentall1/verigate/actions/runs/45336712138) completed successfully; all four jobs passed.
- No local tests were run. All statuses above are GitHub Actions results for the listed workflow runs.

### PR #70 failure root cause: stale synthetic merge base

- The failing test job checked out synthetic merge commit `44b9db339fd486635e7982a2063fe9fe7196d280`, whose merge message says it merged PR #70 head into base `433f600930eeeb1a578cb8bf1c10e6c4f9724aaa`.
- The test log shows 41 import errors with `ModuleNotFoundError: No module named 'core.attestor_history'`. The container job also failed its API health/auth smoke after the image build; its log does not establish the precise startup exception.
- At base commit `433f600...`, `core/attestor_history.py` is absent. Current PR #69 head `93416056...` adds that file (352 lines); fetching it at PR #69 and PR #70 branch refs confirms the module is present there.
- Therefore the failing run exercised an outdated PR #70 synthetic merge base that predates the restoration of the module. Do not repeatedly rerun failed jobs on the same workflow run/SHA; that would reuse stale checkout state. A fresh PR synchronization event/run against the current parent is needed before interpreting #70 CI.
- PR #70 remains open Draft. No branch was force-pushed, retargeted, closed, reopened, or merged in this review.

### PR #73 stack drift: CI did not include latest PR #72 changes

- PR #72 head `b8b2458...` contains the latest three overflow-safe call-site replacements in `core/wallet_enrollment_history.py`: portable request `attested_at`, governance action `issued_at`, and approval `issued_at` now use `_finite_timestamp()`.
- The same file at PR #73 head `81d52d4...` still uses `math.isfinite(float(...))` at those three portable-resolver call sites. Thus PR #73's green run does **not** validate the integrated tree containing the latest PR #72 fix.
- Commit comparison confirms PR #72 head and PR #73 head both descend from `7436fc8572f60740993d2033cbad4809f9954a88`; PR #72 has two commits ahead of that point, while PR #73 has 38. PR #73 has not incorporated those two latest PR #72 commits. Its base is declared as the portable-proof branch, but the checked PR tree remains stale relative to #72.
- Before treating #73 as ready, synchronize its branch with the latest #72 head and rerun CI. Do not manually duplicate the same fix into #73 unless a proper stack synchronization is unavailable; avoid creating duplicate changes or future merge conflicts.

### PR #73 duplicate-node concern resolved

- Initial review concern: `core/offline_verifier.py::_nodes()` builds a dictionary comprehension and could collapse duplicate `(type, id)` graph nodes.
- Follow-up inspection confirms `core/evidence_manifest.py::_verify_nodes()` rejects duplicate node references before `verify_proof()` proceeds to `_nodes()`. The concern is not a demonstrated bypass in the current verification order; no code change is justified for it.
- Transparency-log verification still checks exact history coverage, ordered entry sequence, hash chaining, checkpoint binding, signer fingerprint and signature. With no independent key/checkpoint pins it explicitly reports the checkpoint as unpinned.

### Current safe next steps

1. Reconcile the #70 parent/base branch state and obtain a fresh CI run on a synthetic merge that includes the restored `core/attestor_history.py`; do not retry the stale run.
2. Synchronize PR #73 onto the latest #72 head, preserving the stack, then rerun all four CI jobs and review the integrated diff.
3. Keep #69, #70, #72, #73, #82 and #81 open Draft until dependency order, review and CI evidence are coherent. No PR has been merged.
4. Continue to avoid production credentials, live wallet operations and real funds. The product milestone remains independent external integration with repeated ALLOW and BLOCK evidence, not additional infrastructure.


## 2026-11-24 — refreshed PR #70 and #73 merge-tree validation

### PR #70: fresh run now uses the correct parent

- Added a regression case for an oversized integer (`10**400`) in the single-governor authority-reset timestamp test. Commit: `1c608464d735042cfe4184faefe5c8f1609d94d8`.
- Fresh CI run [45338669504](https://github.com/rudimentall1/verigate/actions/runs/45338669504) checks out synthetic merge commit `7120783`, explicitly merging PR #70 head `1c60846...` into current PR #69 head `93416056...`. This confirms the stale synthetic-base issue is no longer present in this run.
- At checkpoint update, Python tests and contracts passed; container and Anna UI were still running. Do not call the run green until all four jobs finish.
- PR #70 remains open Draft and mergeable. No branch retarget or merge performed.

### PR #73: portable timestamp fix incorporated and tested on the merge tree

- The #73 branch previously retained three unsafe `math.isfinite(float(...))` conversions in the core portable enrollment resolver. Replaced them with the existing overflow-safe `_finite_timestamp()` helper.
- Added the same positive/negative `10**400` regression test to `tests/test_wallet_enrollment_portable.py`.
- Commits: source `e8899624e9406b8a3478783e587cd889e7058f72`; test `66c2fd9faf4af8b1b9b61912fa55dc4f9405777e`.
- Fresh CI run [45338632501](https://github.com/rudimentall1/verigate/actions/runs/45338632501) checks out synthetic merge commit `e5e26be`, explicitly merging PR #73 head `66c2fd9...` into current PR #72 head `b8b2458...`. This is the desired integrated tree for validation.
- At checkpoint update, Python tests, container and contracts passed; Anna UI was still running. Do not call the run green until the fourth job finishes.
- PR #73 remains open Draft and mergeable.

### Additional PR #73 verifier parity review

- Core, standalone CLI and packaged verifier implementations of the transparency bundle checks were compared.
- The standalone CLI and packaged verifier files are byte-identical at this head (`92acc3b6...`) and use the same overflow-safe wallet-time helper for checkpoint `issued_at`.
- The core verifier uses `_finite_number()`; the CLI/package copies use `_finite_wallet_time()`. Both reject oversized integers before timestamp conversion.
- The three implementations agree on the key trust semantics: a signature without an out-of-band log-key plus latest-checkpoint pin is explicitly marked unpinned; when pins are supplied, both are required and checked.
- No additional confirmed bypass was found in this pass. This remains source-level review, not a full security approval.

### Current next action

1. Wait for the remaining #70 container/Anna UI and #73 Anna UI jobs; inspect any failure logs rather than blindly retrying.
2. Refresh PR #69/#70/#72/#73/#82/#81 metadata and CI after completion.
3. Keep all PRs Draft and unmerged. Do not claim local tests ran; all validation here is GitHub Actions.


### CI completion follow-up

- PR #73 run [45338632501](https://github.com/rudimentall1/verigate/actions/runs/45338632501) is now fully green: Python tests, container, contracts and Anna UI all passed on synthetic merge commit `e5e26be` (PR #73 head merged into PR #72 head).
- PR #70 run [45338669504](https://github.com/rudimentall1/verigate/actions/runs/45338669504) remains in progress: Python tests and contracts passed; container and Anna UI are still running.


## 2026-11-24 — PR #66 oversized timestamp hardening

### Reproduced defect and fix

- PR #66 head before this work: `59ab13baa9df69c4a0ffe2f209498efea778777d`.
- Added `test_authority_lifecycle_rejects_oversized_timestamps_without_overflow` in `tests/test_reference_lifecycle.py`. It mutates signed proof data with both positive and negative `10**400` values for governance action `issued_at/expires_at`, governance approval `issued_at/expires_at`, and outcome attestation `attested_at`; it exercises both core `verify_proof()` and the standalone CLI.
- Test-first CI run [45342018445](https://github.com/rudimentall1/verigate/actions/runs/45342018445) reproduced the bug: Python suite failed with 16 `OverflowError` errors. Logs confirmed the core validator overflow and a second overflow in `verify_governance_approval()` while subtracting huge approval timestamps.
- Added overflow-safe `_finite_timestamp()` parsing in `core/proof_validators/authority_lifecycle.py` and `tools/verigate_proof_verifier.py`. Both governance interval boundaries are validated before the quorum verifier performs timestamp arithmetic; attestation, attestor creation, expiry and revocation timestamps use the same safe conversion.
- Regression test passed in CI run [45342141269](https://github.com/rudimentall1/verigate/actions/runs/45342141269): Python suite **676 tests OK**, container and contracts passed; Anna UI was still in progress at the time of this checkpoint.
- A follow-up style-only commit moved the core helper below imports. Latest PR #66 head at checkpoint time: `3996d7d6361acef091a9173ab99faaeeb16e8cd3`. Fresh CI run [45342240003](https://github.com/rudimentall1/verigate/actions/runs/45342240003): Python tests, container and contracts passed; Anna UI remained in progress.
- Local tests were not run because the runtime could not resolve GitHub for cloning. All reported verification is GitHub Actions.

### Merge sequencing

- PR #66 targets `main`; PR #67 targets branch `fix/offline-governance-proof-validation` and therefore depends on #66. PR #67's recorded base SHA is still the pre-fix #66 head `59ab13b...`; refresh/reconcile this stack edge after #66 is merged.
- Do not merge #67 or later stack PRs ahead of their parents. Once #66 is accepted, retarget/reconcile #67 to the new base and validate its integrated tree before proceeding.
- PR #66 remains Draft and unmerged at checkpoint time. No production services, keys, wallets, contracts, or funds were touched.


### PR #66 final CI and review hand-off

- Final head `3996d7d6361acef091a9173ab99faaeeb16e8cd3` has CI run [45342240003](https://github.com/rudimentall1/verigate/actions/runs/45342240003) completed successfully across all four jobs: Python tests, contracts, container and Anna UI.
- PR #66 description was refreshed with the overflow fix and verification evidence, and the PR was moved from Draft to Ready for review.
- Requested the repository's configured Codex code review by marking the PR ready and explicitly requested a security review. The review status was still `running` at checkpoint time; no review findings or approval had been returned yet.
- PR #66 is mergeable according to GitHub. Main has advanced by two commits since the PR's original base; GitHub reports no merge conflict. The merge commit preview is `715f06438c8dd9ba80dc19620ff575c84e212f54`.
- Do not merge until the configured code/security review completes and any findings are resolved. PR #67 remains stacked on the #66 branch and will be reconciled after #66 lands.


## 2026-11-24 — PR #66 historical attestor lifecycle hardening

### Codex review finding and remediation

- The first Codex code review of PR #66 head `3996d7d...` reported P2: outcome attestations became unverifiable after a later attestor key rotation or revocation because export and offline verification used the current registry record instead of the state effective at `attested_at`.
- Added test-first integration regressions for both post-attestation key rotation and post-attestation revocation. The first CI attempt reproduced the issue; subsequent failures exposed two related integration gaps: lifecycle governance nodes were incorrectly treated as singletons, and the revocation test initially omitted the historical authority snapshot when rebuilding the graph.
- Implemented historical attestor resolution from governance-signed lifecycle actions in `core/outcome.py` and `core/proof_validators/authority_lifecycle.py`. The verifier now reconstructs the effective key, type, expiry and active/revoked state at the attestation timestamp and verifies the outcome signature against that historical key.
- Updated the evidence graph builder to deduplicate shared governance-policy nodes, and adjusted proof-profile validation so governance actions and approvals are treated as a multi-node history rather than singleton evidence.
- Existing forged-attestation and unapproved-key-substitution tests remain covered.

### Latest validation

- PR #66 latest head: `3492aea34e580aefb9e3078a6130c64926776e9b`.
- GitHub Actions run [45346927853](https://github.com/rudimentall1/verigate/actions/runs/45346927853): **all four jobs passed** — Python tests, contracts, container and Anna UI.
- Python suite: **680 tests passed**.
- New regressions: later key rotation and later revocation both preserve offline verification of the earlier attestation.
- Local tests were not run; validation is from GitHub Actions only.
- PR #66 description refreshed with the historical lifecycle fix and exact CI evidence. PR remains open, Ready for review, mergeable and unmerged.
- Requested a fresh Codex code review and security review on the updated head. The code review was still running when this checkpoint was updated; security-review status had not yet appeared. The earlier P2 thread is not yet marked resolved.
- PR #67 remains stacked on PR #66's branch and has not yet been rebased/reconciled onto the post-merge main. Do not merge #67 ahead of #66.

### Next action

1. Wait for fresh code/security review on #66 head `3492aea...`; inspect every new finding and resolve the P2 thread only after evidence supports closure.
2. If review is clean, recheck the latest head and all four CI jobs, then merge #66 using an expected-head SHA.
3. Reconcile #67 onto updated `main`, verify it contains the #66 historical-attestor and timestamp fixes, rerun CI and continue the stack in dependency order.
4. Keep the adoption milestone unchanged: an independently maintained external integration with repeatable authorized ALLOW and unauthorized BLOCK evidence.


### PR #66 follow-up — application-time and standalone parity

- A second security pass found that using only action `issued_at` could apply a pre-issued governance action retroactively, before its full approval quorum existed. The durable attestor governance envelope already records `recorded_at`; evidence export now carries this as issuer-signed `effective_at` on the governance-action evidence node.
- Core export, core offline verification and standalone CLI now require `effective_at` to be finite, no earlier than the first instant the complete quorum existed, and before the action expiry. Historical lifecycle reconstruction uses this application time, not the action creation time.
- The standalone verifier previously still compared the current attestor record. It now independently reconstructs the historical key/type/expiry/status and verifies the outcome signature against that historical state, matching core behavior.
- Added CLI regressions for historical attestation after rotation, historical attestation after revocation, and rejection of a governance action whose recorded application time predates its quorum.
- PR #66 latest head: `30f363b9e3d4a16eb5224bbb9fb4a7daa14c00b1`.
- GitHub Actions run [45347792345](https://github.com/rudimentall1/verigate/actions/runs/45347792345): **all four jobs passed**. Python suite: **682 tests passed**; contracts, container and Anna UI also passed.
- PR description refreshed with application-time semantics and the standalone verifier parity work.
- Codex review for head `3492aea...` completed with no major issues, but it predates the latest `effective_at` and standalone CLI changes; the original P2 thread remains unresolved. Fresh code and security reviews were requested for head `30f363b...`; latest review status was not yet available at checkpoint update.
- PR #66 remains open, Ready for review, mergeable and unmerged. Do not merge until the latest-head review is complete and the P2 thread is addressed.


### PR #66 chronology hardening and final CI refresh

- Added chronological-order enforcement for attestor governance application timestamps in core and standalone verifiers. The verifiers no longer sort a malformed history into an apparently valid sequence; they reject a proof whose governance-action node order moves backward in effective time.
- Added an adversarial regression that reorders the registration and rotation governance-action nodes, re-signs the manifest, and confirms both verifiers reject the proof.
- Latest PR #66 head: `db8f44d3b657550f9194eaaa323a08f75a1b9671`.
- Latest CI run [45348317628](https://github.com/rudimentall1/verigate/actions/runs/45348317628): **all four jobs passed** — Python tests, contracts, container and Anna UI.
- Python suite: **684 tests passed**. The rotation, revocation, pre-quorum application-time and reordered-history regressions all passed in both core and standalone paths.
- PR #66 description refreshed to match head `db8f44d...` and run `45348317628`. GitHub still reports the PR mergeable and Ready for review.
- Fresh Codex code review and security review were requested for head `db8f44d...`; status is pending at checkpoint update. Do not use the earlier review of `3492aea...` or the review in progress for `30f363b...` as approval of this latest head.
- The original P2 review thread remains unresolved until the latest-head review confirms the remediation. PR #66 remains unmerged.

- The original Codex P2 review thread was marked resolved after the historical-state, application-time, standalone parity and chronological-order fixes passed the latest four-job CI run. Fresh Codex code review on `db8f44d...` is still running; security-review status remains unreported.


### PR #66 follow-up — preserve revoked state on key rotation and policy overflow

- A new adversarial regression found that `Storage.rotate_outcome_attestor()` explicitly set `status='ACTIVE'` and cleared `revoked_at` during key rotation. This bypassed the separate `ATTESTOR_ACTIVATE` governance action.
- Fixed storage rotation to update key/type/expiry only; it now preserves current authority status. Core runtime history reconstruction, portable core verifier and standalone CLI also preserve the prior status when replaying `ATTESTOR_ROTATE`; only `ATTESTOR_REGISTER` initializes ACTIVE and `ATTESTOR_ACTIVATE` reactivates.
- Test-first evidence: the regression failed on the old behavior with `AssertionError: PermissionError not raised`. After the storage correction, the test verifies a forged post-revocation attestation using the rotated key is rejected by core and standalone proof verifiers, and runtime refuses to record it.
- Codex review on previous head `db8f44d...` found a second P2: `GovernancePolicy.from_dict()` can raise `OverflowError` on an infinite numeric version before signature validation. Added `OverflowError` to the fail-closed exception handling in `core/proof_validators/authority_lifecycle.py` and the evidence export path `core/evidence.py`.
- Added regression with an infinite governance-policy version; core returns invalid proof and standalone CLI fails closed. Test-first CI reproduced the unhandled `OverflowError` before the fix.
- Latest PR #66 head: `9fe699109c8f0b8acdef18e060c89074d12861a3`.
- Latest CI run [45350535895](https://github.com/rudimentall1/verigate/actions/runs/45350535895): **all four jobs passed** — Python tests (**688 passed**), contracts, container, Anna UI.
- PR description updated with both fixes and current trust boundaries. Both P2 review threads (historical attestor and overflowing policy) are marked resolved.
- Fresh Codex code review for `9fe6991...` is running. Security-review status is still not reported. PR #66 remains open, Ready for review, mergeable and unmerged. Do not merge until latest-head review completes and no new findings remain.


## Current authoritative status — 2026-11-24 07:56 UTC

This section supersedes earlier "unmerged/pending" statements above where they conflict with the current repository state.

### PR #66 — merged

- PR [#66](https://github.com/rudimentall1/verigate/pull/66) was squash-merged into `main` at 2026-11-24 07:52 UTC.
- Merge commit: `c3f03d4ee58c633a4a337cc2602d380e25544824`.
- Final PR head: `9fe699109c8f0b8acdef18e060c89074d12861a3`.
- Latest Codex code review receipt for that exact head: "Didn't find any major issues."
- Both recorded P2 review threads were resolved before merge.
- GitHub Actions run [45350543030](https://github.com/rudimentall1/verigate/actions/runs/45350543030) completed with all four jobs successful: Python suite, contracts, container and Anna UI. The Python suite step passed; PR #66 records 688 tests.
- A separate Codex security-review request was posted, but no distinct security-review receipt/status was returned. Do not claim a separate security review completed.

### PR #67 — rebased onto main, validation pending

- PR [#67](https://github.com/rudimentall1/verigate/pull/67) remains open and Draft; base is now `main`.
- Its branch was rebuilt on top of merge commit `c3f03d4...` to avoid replaying the 58-commit history of squash-merged PR #66.
- Current head: `d402f2325b3008e68313680516d3d009ff53b0df`.
- Compare against main confirms exactly 3 commits and only the intended 3 changed files: `docs/verigate-authority-proof-v1.md`, `tests/test_reference_lifecycle.py`, and `tools/verigate_proof_verifier.py`.
- The current verifier includes PR #66's timestamp, historical-attestor, revocation-preservation and overflow fixes, plus the governance-policy pin option.
- GitHub Actions run [45351724156](https://github.com/rudimentall1/verigate/actions/runs/45351724156) is running on this exact head. Earlier CI for the old pre-rebase head is historical evidence only and must not be used as current-head validation.
- Fresh Codex code review and security review were requested for `d402f232...`; no results have been received yet.
- Keep #67 Draft until the current-head CI and review results are inspected. Do not merge based only on the old 684-test run.

### PR #81 checkpoint branch refresh

- Rebase onto current `main` is complete; this checkpoint branch no longer retains stale ancestry after #66's squash merge.
- It remains documentation-only; no runtime or production behavior is changed.

### Immediate next steps

1. Inspect all jobs in PR #67 run `45351724156`; investigate failures rather than reusing old-head results.
2. Read the new Codex code-review and security-review responses for exact head `d402f232...`; resolve any findings with regression tests.
3. If CI and review are clean, mark #67 ready, recheck the head SHA and mergeability, then merge using an expected-head SHA.
4. Continue the remaining stacked PRs in dependency order. Do not retarget or cherry-pick downstream PRs without checking their merge-base and complete integrated diff.
5. Keep the product milestone unchanged: one independently maintained external integration with repeated, inspectable ALLOW and BLOCK evidence at the execution boundary.


### PR #67 current-head CI completion — 2026-11-24

- Rebased PR #67 head `d402f2325b3008e68313680516d3d009ff53b0df` has completed GitHub Actions run [45351724156](https://github.com/rudimentall1/verigate/actions/runs/45351724156): all four jobs passed.
- Python suite: **698 tests OK**.
- Contracts, container/API-auth, Anna UI E2E and Linux binary smoke all passed.
- Fresh Codex code review for this exact head remains running. The separate security-review request has no returned status/receipt yet.
- PR #67 remains Draft and unmerged pending review completion. No local tests were run.


## PR #67 merge completion — 2026-11-24 07:58 UTC

- PR [#67](https://github.com/rudimentall1/verigate/pull/67) was squash-merged into `main` at 2026-11-24 07:58 UTC.
- Merge commit: `c11dca3b8e0ecdd0422168a5e352de4d0574c9d6`.
- Merged head: `d402f2325b3008e68313680516d3d009ff53b0df`.
- Exact-head GitHub Actions run [45351724156](https://github.com/rudimentall1/verigate/actions/runs/45351724156): all four jobs passed; Python suite **698 tests OK**, contracts, container/API-auth, Anna UI E2E and Linux binary smoke passed.
- Codex code review for the exact head completed with no findings.
- A separate security-review request had no distinct receipt/status. Do not claim a completed security review.
- PR #67's branch was rebuilt on top of #66's squash merge before merging, and its diff was verified to contain only the three intended files. No duplicate #66 changes were reintroduced.
- PR #66 and #67 are now both merged into main. No local tests were run.

### Current next steps

1. Refresh the remaining stacked PR metadata and verify dependency ancestry before changing any bases.
2. Continue the stack in dependency order; preserve merge-base integrity and validate each integrated tree with current-head CI.
3. Keep the independent external integration milestone as the product priority. Infrastructure expansion is not a substitute for repeated external ALLOW/BLOCK evidence.


## PR #68 rebase and snapshot-consistency hardening — 2026-11-24

- PR [#68](https://github.com/rudimentall1/verigate/pull/68) was rebuilt on current `main` after #66/#67 squash merges. Current head: `eacff3fd88e08ef394a7407bc30b45dd1e3de99d`.
- The rebased diff is 7 commits / 4 files only: `core/evidence.py`, `core/proof_validators/authority_lifecycle.py`, `tools/verigate_proof_verifier.py`, and `tests/test_reference_lifecycle.py`.
- Test-first run [45352821577](https://github.com/rudimentall1/verigate/actions/runs/45352821577) reproduced two failures: an ACTIVE registry snapshot inconsistent with a later governance revocation was accepted, and a reused policy-node digest with different content was silently deduplicated.
- Fixed both core and standalone verifiers to replay the full governance history, compare the final signed registry snapshot against the replayed state, and select the historical key/status at attestation time. Key rotation preserves prior status; activation retains the revocation marker in the current snapshot but clears it from the historical active authority view.
- Evidence export now rejects different policy content under an existing governance-policy node ID.
- Added a reactivation regression covering both core and standalone paths.
- Current-head GitHub Actions run [45353320943](https://github.com/rudimentall1/verigate/actions/runs/45353320943): all four jobs passed; Python suite **704 tests OK**, contracts, container/API-auth, Anna UI E2E and Linux binary smoke passed.
- Fresh Codex code review and security review were requested for exact head `eacff3f...`; code review is still running and no separate security-review receipt/status has been returned. PR #68 remains Draft and unmerged.

### Next stacked PR risk — #69

- PR #69 remains based on the old #68 head and must be rebased after #68 is accepted.
- Source review of its current `core/attestor_history.py` found that `ATTESTOR_ROTATE` sets state to ACTIVE and clears `revoked_at`. This conflicts with the #66 invariant that key rotation must preserve revoked/expired authority state. Fix with a test-first regression before #69 can merge.
- The same module has timestamp conversions that need overflow-safe validation; PR #82 contains related hardening, but must be reviewed on the integrated rebased tree.


### PR #68 latest head and transition-state regression — 2026-11-24

- PR #68 head advanced to `48e7a7f076e55ff4c34eac503971e50d481c2f60`.
- Added a test-first regression for repeated `ATTESTOR_REVOKE`; the red run [45353938356](https://github.com/rudimentall1/verigate/actions/runs/45353938356) showed both core and standalone verifiers accepted the invalid repeated transition.
- Both verifiers now require revocation to follow ACTIVE state. Rotation continues to preserve existing status/revocation marker; activation retains the marker in the current snapshot.
- Current-head GitHub Actions run [45354080414](https://github.com/rudimentall1/verigate/actions/runs/45354080414): **all four jobs passed**, Python suite **706 tests OK**, including Anna UI E2E and Linux binary smoke.
- Exact-head Codex Code Review for `48e7a7f...` completed with no findings before the PR was marked Ready for review. Marking it Ready triggered another review cycle, which is currently running; a separate security-review receipt/status has not yet been returned. PR #68 is Ready for review and remains unmerged.

### PR #69 additional source-review findings

- In addition to the rotation-state issue already recorded, `core/attestor_history.py` currently sorts governance actions by effective time before checking monotonic order. This can normalize malformed/out-of-order persisted history instead of rejecting it. Preserve source order and reject non-monotonic input with a regression test.
- The module also contains numeric-to-float conversions that need explicit overflow-safe handling; inspect together with PR #82's deserialization hardening after rebasing.


### PR #68 / #81 follow-up status — 2026-11-24

- PR #68 was marked Ready for review after the exact-head code review of `48e7a7f...` completed without findings and the 706-test CI run passed all four jobs.
- The Ready transition triggered a fresh Codex review cycle for the same head; it is running. A separate security-review receipt/status is still absent despite an explicit request. Do not merge until the fresh review finishes and security review is resolved or explicitly determined not to be a required gate.
- PR #81's P3 checkpoint wording finding was fixed: the document now says the rebase onto `main` is complete. Its review thread is resolved. Updated-head CI run [45357618214](https://github.com/rudimentall1/verigate/actions/runs/45357618214) has Python, contracts and container jobs passed; Anna UI E2E was still running at last poll.
- PR #81 was re-reviewed on the updated head `d15ad99...`; the new review request is pending.
- PR #69 remains stacked on the pre-final #68 head and is not ready to rebase or merge until #68 lands. Its source review found rotation reactivating revoked state, sorting before validating chronological input, and unguarded numeric-to-float conversions in `core/attestor_history.py`.


## Architecture quality audit pilot — 2026-11-28

- Created feature branch `chore/deslop-please-architecture-audit` from the previously observed `main` head `0c9e9393e6b7621994e00abbfee0c7e74aa85094`.
- Added an advisory GitHub Actions workflow at `.github/workflows/architecture-audit.yml`.
- Added `docs/ARCHITECTURE-QUALITY.md` and extended `AGENTS.md` with review rules.
- The workflow pins `deslop-please` to `cfabfb9ee417e150d5342e8ef0d6a0fe725cc9a0`, Rust `1.99.0`, `scip-python` `0.6.8`, and `scip-typescript` `0.5.2`.
- It discovers supported Python, TypeScript, and JavaScript projects. Solidity is not supported and is explicitly out of scan scope.
- JSON diagnostics and indexer stderr are retained as a 14-day Actions artifact. Findings and scan-time errors are advisory and do not gate the existing Verigate CI; installation/setup failures still fail this separate workflow.
- No application source, runtime dependencies, lockfiles, authorization rules, contract behavior, or release artifacts were changed. No allowlist or automatic source rewrite was introduced.
- First GitHub Actions attempt `46112222180` installed Rust `1.99.0` and Node.js `22.23.5`, but Cargo rejected the install command because the tool repository also contains fixture binaries. No SCIP indexer or source scan ran in that attempt.
- Corrected the workflow and local instructions to select the `deslop-please` package explicitly after `--locked`. The final Architecture Audit run [46112311890](https://github.com/rudimentall1/verigate/actions/runs/46112311890) completed successfully as a GitHub Actions job, with tool installation, both SCIP indexers, source scan, and report upload all confirmed.
- The analyzer itself returned exit code `1` and reported **17 diagnostics**: 1 `module-cycle`, 11 `field-leak`, 4 `wide-directory`, and 1 `long-file`. Details and limitations are recorded in `docs/ARCHITECTURE-QUALITY.md`. The report artifact is [15249918282](https://github.com/rudimentall1/verigate/actions/runs/46112311890/artifacts/15249918282).
- The first PR functional CI attempt `46112311881` had a transient Anna UI E2E failure at `one-time execution permission is issued only after a separate user click` while checking `execution permission signature verified`. The failed Anna UI job was rerun in place and passed, including the Linux Anna Executa binary build/smoke; the rerun completed with all four jobs successful: Python test suite, contracts, container/API-auth, and Anna UI. This verifies the code-equivalent source head `f0a830c...`.
- The later documentation-only PR head `a1f0e1f...` triggered a fresh functional CI run `46112525458`, which was still in progress at this checkpoint refresh. No application source files changed after the fully successful rerun above; do not describe the newer run as completed until its final status is observed.
- No application source or authorization logic was changed to address the scan. No allowlist or source rewrite was introduced. Solidity was not scanned, and this result is not a security audit.

## Architecture cycle remediation — 2026-11-28

- Opened Draft PR [#88 — break core/enforcement dependency cycle](https://github.com/rudimentall1/verigate/pull/88).
- Initial scan run [#46112311890](https://github.com/rudimentall1/verigate/actions/runs/46112311890) reported one cycle across `attest`, `core`, and `enforcement`. The report identified two misplaced modules: `core/adversarial.py` imported attestation verification, and `core/genesis_lifecycle.py` imported `enforcement.router.ExecutionRouter`.
- Moved the adversarial harness to `attest/adversarial.py` and Genesis orchestration to `application/genesis_lifecycle.py`. Updated the API import and tests, then removed the old core modules. No signature, authorization, replay, execution, or side-effect behavior was changed.
- TDD RED was confirmed by [CI #46115786079](https://github.com/rudimentall1/verigate/actions/runs/46115786079): expected missing-module failures occurred before implementation.
- The implemented source passed [CI #46115841371](https://github.com/rudimentall1/verigate/actions/runs/46115841371): **698 Python tests**, **69/69 Anna UI E2E**, contracts, container/API-auth, and Linux Anna Executa 0.1.18 smoke all passed.
- Dependency boundaries are documented in `docs/ARCHITECTURE-DEPENDENCY-BOUNDARIES.md`, included in PR #88, and agent rules have been updated on this architecture-doc branch.
- **Architecture scan re-run pending:** the Architecture Audit workflow is not yet on `main`. Do not report the cycle count as zero from the analyzer until a fresh report is produced. No live chain execution was performed.

## Expanded package-cycle remediation — 2026-11-28

A fresh source review after the first two module moves found a second-cycle cause. Analyzer run [#46116545770](https://github.com/rudimentall1/verigate/actions/runs/46116545770) reported the remaining two-package cycle as `core/authorization.py -> attest` and `attest/authority_replay.py -> core`. Manual review also found the reverse dependency in `core/evidence.py`.

Additional PR #88 changes:
- Concrete authorization issuance moved from `core/authorization.py` to `attest/authorization.py`; `core.authorization` now contains only the dependency-inversion Protocol `AuthorizationArtifactIssuer`.
- `core.engine.GuardrailEngine` accepts the issuer by injection. New `application.engine.GuardrailEngine` composes the core engine with the concrete attestation issuer for runtime/API authorization flows.
- Evidence graph construction and snapshot service moved from `core` to `attest`; historical replay remains in `attest`.
- Updated API, adapters, Genesis orchestration and all discovered test imports. Removed the old evidence modules from `core`.
- Governed wallet enrollment is in `application.wallet_enrollment`; Genesis lifecycle is in `application.genesis_lifecycle`.

Current source has not yet been verified by a completed post-change full CI and architecture scan. The last analyzer result (#46116545770) predates these extra moves and must not be used to claim zero cycles. Re-run both workflows against the final head and inspect the complete diagnostic JSON/artifact.

### Portable proof verifier moved into the attestation layer — 2026-11-28

The current-head analyzer report [#46120175666](https://github.com/rudimentall1/verigate/actions/runs/46120175666) still found a single cycle caused by `core/offline_verifier.py` importing signed authorization/receipt verification from `attest`. Together with the reverse `attest/authority_replay.py -> core` dependency, this created the last `core <-> attest` cycle.

Moved both related transport/verification modules into their owning package:
- `core/offline_verifier.py` → `attest/offline_verifier.py`
- `core/proof_package.py` → `attest/proof_package.py`

Updated the callers in the CLI, Genesis lifecycle, proof/evidence tests, authority proof protocol vector test and portable proof artifact test. Also fixed remaining compatibility imports found by CI:
- Anna Executa plugin now creates `application.engine.GuardrailEngine`.
- Chain verifier worker reads installation-principal derivation from `application.wallet_enrollment`.
- Execution router and demos import concrete `AuthorizationService` from `attest.authorization`.
- Anna state-initialization test patches the application composition root.
- `tests/test_engine.py` now tests the application engine for signed authorization behavior and uses the core engine only for the fail-closed missing-issuer regression.

CI on the earlier revision found stale imports and missing caller migrations; those are not hidden as successful verification. Fresh full CI and architecture scan for the current branch head are pending. Do not mark the module cycle resolved until the new architecture report confirms zero `module-cycle` diagnostics.
