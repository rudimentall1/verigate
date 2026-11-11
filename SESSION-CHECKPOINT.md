# Verigate Session Checkpoint

**Updated:** 2026-11-11
**Current work branch:** release/arc-security-consolidation-2026-11-11
**Default branch:** main
**Primary objective:** safely consolidate the Arc Authority Registry integration, close production security gaps, and produce independently verifiable evidence.

## Immediate truth
- Do not claim finality faster than Arc. Measure Verigate authorization latency separately from Arc consensus finality.
- Do not claim the Arc Registry is a global USDC firewall. It records/consumes authority; direct out-of-band wallet transfers remain possible unless an on-chain account/guard constrains them.
- Do not claim the Verigate Arc integration is already in main. PR #38 is open, Draft, and divergent.
- Do not claim an independently verified Verigate-authorized Arc payment. Existing Guardian v3 payment evidence belongs to a separate project.
- Do not claim Verigate is unhackable or independently audited.

## Branch and PR state from latest GitHub inspection
- PR #38 Arc Authority Registry: head f00fca98ad20ea0b9bb052d01a36e8e77a11c9ad, 30 commits ahead / 40 behind main, mergeable=false.
- PR #40 secure Docker defaults: head 868f75edb80189c18fbfa299effb6eb31dad91b1, 1 commit ahead / 35 behind main, mergeable=false.
- PR #41 late Arc confirmation regression: head a81d96c8764dcfbe72bee6bf5c3196ad8370d521, based on Arc branch.
- PR #42 external agent SDK: head ea64c89880e09e23ca4c324294de33733a8f9338, based on Arc branch.
- Consolidation branch created from current main: release/arc-security-consolidation-2026-11-11.
- No PR has been merged and no production server, contract, wallet or transaction has been changed in this session.

## Arc branch implementation to port
- Signed Arc payment intent, identity/capability/policy checks.
- Registry registration and one-time consumption.
- Arc-specific confirmation endpoints and generic-consume bypass rejection.
- Full event topic comparison and regression tests.
- Receipt, calldata, sender, destination, block hash/timestamp and Registry state checks.
- Non-custodial EIP-1193 client with separate explicit payment broadcast.
- External agent SDK/enrollment kit and late-confirmation regression from PR #41/#42.
See PR #38, #41, #42 and docs/SECURITY-ARC-COMPLETION-PLAN.md.

## Critical security gaps
1. Main direct Python launch remains open by default unless auth flags are set. Docker/Compose defaults are not yet hardened on main.
2. Unsigned capability authority path remains available unless VERIGATE_REQUIRE_SIGNED_INTENT=1.
3. Issuer private key is local-file based; no KMS/HSM or complete rotation system.
4. Registry owner/issuer governance needs stronger operational controls (multisig/rotation/revocation).
5. Runtime Registry bytecode hash is not pinned to a reproducible reviewed artifact.
6. Explicit Arc finality/provider trust policy is incomplete.
7. RPC is a trust boundary; independent provider/node cross-checks are incomplete.
8. On-chain consumed/local failed recovery needs a documented, tested fresh-authorization workflow.
9. Handler child effects and out-of-band wallet actions are outside the current execution boundary.
10. No independent penetration test or external security audit.

## Performance target
- Initial target: local authorization decision p95 below 100 ms under a documented benchmark.
- Initial target: server-side pre-broadcast path p95 below 500 ms, excluding user confirmation, wallet signing, RPC inclusion and Arc consensus finality.
- Arc settlement finality remains Arc's own protocol property. Never compare this with API latency as if they were the same metric.
- These are targets only; no benchmark has yet been run.

## Execution order
1. Port secure container defaults from PR #40 while preserving current main CI and Anna version.
2. Reconcile Arc PR #38 files onto this branch, preserving newer main changes.
3. Port PR #41 and #42 after conflict review.
4. Implement bytecode pinning, Arc finality policy, recovery semantics and adversarial tests.
5. Run full CI on exact consolidation head.
6. Review diff and create one consolidated PR to main.
7. Merge only when exact-head checks pass; verify resulting main SHA and CI.
8. Only then proceed to independently verify deployed Registry and perform explicitly approved live transactions.

## Hard boundaries
- No force-push.
- No blind merge of divergent branches.
- No production server deployment or restart.
- No Registry redeployment or owner/issuer changes.
- No private-key handling or wallet broadcast.
- No claim that a transaction occurred without independently verifiable transaction evidence.
