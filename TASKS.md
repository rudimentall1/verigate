# Tasks

## Arc consolidation — current branch

### In progress
- [x] Reconcile all 14 post-fork mainline commits into the Arc branch without dropping the current-main security and Anna fixes; GitHub reports PR #86 mergeable.
- [x] Integrate the reviewed Arc Mainnet deployment artifact verifier, historical source/runtime manifest, provenance document and read-only CI workflow.
- [x] Integrate the Guardian Arc agent bootstrap utility; add finite-limit, EVM-target, key-permission/symlink and active-record guards plus regression tests.
- [x] Focused Python, Node, Solidity and signer deployment checks passed in CI on the consolidated branch; latest head: 716 Python tests, contracts and container pass. Latest Anna UI E2E job is still in progress.
- [ ] Run the complete CI matrix and record exact run IDs/commit SHA.
- [ ] Reconcile npm audit --omit=dev advisories with the production dependency tree (27 reported; Ganache and its 27 audit-only packages are absent from npm ls --omit=dev).
- [ ] Review the final diff for secrets, generated artifacts, stale snapshots and unrelated Anna changes.
- [ ] Update this file, docs/SESSION-CHECKPOINT.md and docs/arc/UNIFIED-ARC-CHECKPOINT.md with the verified final state.

### Release gates (not authorized by this source consolidation)
- [ ] Independently review production host account/group/socket ACL mapping.
- [ ] Approve and provision separate issuer and agent signer keys.
- [ ] Set production gas/fee ceilings and daily budgets from representative evidence.
- [ ] Approve controlled target-host installation.
- [ ] Execute and independently verify a live Verigate-authorized Arc USDC payment.

## Explicitly not done
- No production service installation or restart.
- No private-key provisioning.
- No live transaction broadcast.
- No claim of live Verigate-authorized payment settlement.