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
