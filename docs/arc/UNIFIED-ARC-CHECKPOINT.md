# Unified Arc integration checkpoint

**Date:** 2026-11-26  
**Branch:** integration/arc-unified-2026-11-26  
**PR:** https://github.com/rudimentall1/verigate/pull/86  
**Base:** main at d03d1389b9c32ee6014a8165645ff553709abf46

## Consolidated Arc scope

The consolidated branch brings the current Arc implementation into one workstream:

- Arc Mainnet authority registry integration and API lifecycle already present in the mainline baseline.
- Agent-signed Arc payment authorization and settlement confirmation (PR #57).
- Headless agent payment executor and role-isolated signer service (PR #58).
- Unix-domain socket boundaries, separate issuer/agent identities, durable operation journal, replay protection, fail-closed crash recovery and systemd assets.
- Historical deployed Registry source/runtime snapshot, manifest, provenance document and read-only mainnet verifier (PR #56).
- Guardian Arc agent bootstrap helper (PR #25), with additional input/key-file validation and regression tests.

Historical Arc branches are not all independent implementations. The Arc mainnet integration was previously merged through PR #21; authority/security consolidation was merged through PR #53. PRs #55–58 and #25 have been superseded and closed after their relevant implementation was transferred into this branch. Old refs such as integration/arc and integration/arc-authority remain historical references; their complete trees must not be merged mechanically.

## Mainline synchronization

The Arc signer stack originally diverged from current main by 14 commits. Those mainline file changes have now been reconciled by bringing the exact current-main versions of the affected files into this branch, including:
- portable-proof governance/attestor verification and associated tests;
- Anna wallet-hand-off hardening and test isolation;
- current README, release status and documentation checkpoint.

The consolidation PR reports mergeable after this content reconciliation. This is a clean-merge indication, not an approval to merge.

## Mandatory repository documentation

Root files:
- AGENTS.md — mandatory repository discovery, factual accuracy, documentation update and final documentation validation rules.
- PROJECT_CONTEXT.md — project architecture, repository layout and Arc trust boundaries.
- TASKS.md — consolidation, verification and release gates.
- DECISIONS.md — Arc architecture and safety decisions.

## Verification status

- Read-only Arc Registry artifact verifier: passed in workflow run 45786466780 on commit bb0087685dbfea32aa95be5c65492fc5b7552657.
- First Python suite attempt: 679 tests, one failure in the test harness because argparse parsed -inf as an option. The application correctly rejected non-finite values; the test input was corrected to use --max-usdc=-inf.
- Latest full CI run after the test correction and mainline reconciliation: pending; check PR #86 checks and branch workflow runs before treating the branch as ready.
- No local tests were run in this session.
- No production key provisioning, target-host installation/restart, or live Arc payment was performed.

## Remaining gates

1. Confirm all four CI jobs pass on the final branch head.
2. Perform final security review of Arc signer, bootstrap and deployment verifier diffs.
3. Keep PR #86 Draft until those gates pass.
4. Merge into main only after review/approval.
5. Treat production host deployment, key provisioning and live payment as separate approvals.


## Read-only RPC availability correction

The deployment verifier initially failed on subsequent CI runs because the Arc-operated RPC returned no deployment receipt for a historical transaction, although an earlier run on the same artifact passed. The verifier remains fail-closed; it does not treat a missing receipt as success.

To avoid depending on a single RPC's historical transaction availability, the verifier now tries the Arc-operated endpoint first and the independent dRPC Arc Mainnet endpoint second. It requires chain ID 5042 from whichever endpoint is selected, then performs the same deployment transaction/receipt, canonical block, runtime hash, owner, issuer, finalized-head and historical Registry activity checks. If neither endpoint provides complete data, verification still fails.

The dRPC Arc endpoint is listed among Arc Mainnet RPC endpoints by the independent provider directory: https://www.diadata.org/map/web3-builder-hub/arc-rpcs/. The verifier does not submit transactions.


## Final review notes and current checks

- Arc Registry read-only verification passed on the current verifier implementation at commit d6af57d386b5234510d92e8423d76278d4aa0055: workflow run 45787866972. The run used the Arc-operated RPC with the configured independent dRPC fallback and completed successfully.
- Full CI run 45787642323 passed all four jobs on commit 6811972138d189fa19c3d76650c6d0eaeb610d2d. This was before the final mandatory-recipient-allowlist regression test was added.
- The allowlist change exposed a test setup issue: the private-key permission test omitted the now-required valid target, so the CLI correctly stopped earlier. The test now supplies a valid allowlist before asserting the permission rejection.
- Full CI for the corrected latest code head 6885af76a7558d5fe0a59e9fbff69b3d1ad27ff7 is queued as run 45788098288. Do not mark the latest head fully verified until it completes.
- Dependency audit note from the successful contracts job: npm audit reported 36 total advisories and npm audit --omit=dev reported 27, including 4 critical. The affected packages were found nested under Ganache in package-lock.json; the separate production install/tree check passed and confirmed Ganache plus its 27 audit-only packages are absent from npm ls --omit=dev. This is an audit/lockfile classification discrepancy that needs reconciliation; do not describe it as a confirmed production runtime exposure, and do not ignore the audit output.
