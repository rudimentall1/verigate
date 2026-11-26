# Tasks

## Arc consolidation — current branch

### In progress
- [ ] Resolve conflicts between the Arc signer/payment stack and current main without dropping post-branch security fixes.
- [ ] Integrate the reviewed Arc Mainnet deployment artifact verifier and its read-only CI workflow.
- [ ] Integrate the Guardian Arc agent bootstrap utility and validate its scope/security.
- [ ] Run focused Python, Node, Solidity and signer deployment tests on the consolidated branch.
- [ ] Run the complete CI matrix and record exact run IDs/commit SHA.
- [ ] Review the final diff for secrets, generated artifacts, stale snapshots and unrelated Anna changes.
- [ ] Update this file and SESSION-CHECKPOINT.md with verified final state.

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