# Verigate project context

Purpose: Agent Authority Control Plane. An agent proposes an exact consequential action; Verigate evaluates identity, capability and policy; an execution boundary enforces the authorization; evidence supports independent verification.

## Repository shape

This is a mixed Python, Solidity and Node.js repository, not a generic src-only application.
- Python application: api/, core/, attest/, enforcement/, adapters/, integrations/.
- Arc contracts: contracts/arc-authority/.
- Arc implementation and signer services: integrations/, deploy/arc-signer/, deploy/systemd/.
- Arc operations and verification: scripts/.
- Tests: Python tests under tests/test_*.py; Node tests under tests/*.test.mjs; shell deployment/runtime smoke tests under tests/.
- Product and engineering docs: docs/, README.md, AGENTS.md; docs/SESSION-CHECKPOINT.md is the current engineering checkpoint. The root SESSION-CHECKPOINT.md is retained as a legacy checkpoint.

## Arc architecture

- Arc Mainnet chain ID: 5042.
- Canonical Arc USDC ERC-20: 0x3600000000000000000000000000000000000000; ERC-20 amounts use 6 decimals.
- Arc native gas asset uses 18 decimals; ERC-20 transfer transactions carry zero native value.
- Registry address recorded in the Arc implementation: 0x4D09CdD490c1Ce48BCB6DA5c1A6Bf41E2f5e853D.
- Registry is an authority/evidence mechanism, not escrow and not a universal wallet firewall.
- Flow: signed agent intent → Verigate authorization → operator issuer registration → Registry confirmation → agent executor consumption → exact USDC payment → settlement confirmation.
- Issuer and agent signer roles must remain separated. Agent runtime must not have issuer socket/key access.
- Signer service exposes typed operations only (register, consume, payment), uses Unix sockets, durable journal/replay protection and fail-closed recovery.
- The signer is OS-isolated, not an HSM and not protection against root/host compromise.

## Key commands

```bash
PYTHONPATH=. python -m unittest discover -s tests -v
npm run test:arc-client
npm run test:arc-agent-executor
npm run test:arc-constrained-signer
npm run verify:arc-deployment
npm run compile:arc-authority
```

Use commands documented by current workflow/package scripts; do not infer that all commands have passed from historical CI notes.

## Evidence boundaries

- CI tests and local mock-RPC/systemd tests are not live Arc Mainnet payment evidence.
- Registry deployment verification is distinct from a payment broadcast and settlement.
- The separate Guardian v3 live payment is not a Verigate-authorized payment.
- No production signer key provisioning, target-host installation, or live signer payment is implied by this source branch.

## Current consolidation branch

- Branch: integration/arc-unified-2026-11-26.
- Starting implementation head: 42061acc511c188e55b6823a575615dea4e98b3c (Arc signer branch, stacked on Arc payment-settlement work).
- This branch is a consolidation workspace, not a production deployment.
- The 14 post-fork mainline commits have been reconciled by syncing the current-main versions of all affected files. GitHub currently reports the consolidation PR mergeable; fresh full CI and review remain mandatory before merge.