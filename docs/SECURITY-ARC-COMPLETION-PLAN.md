# Verigate Security and Arc Completion Plan

**Updated:** 2026-11-11
**Repository:** rudimentall1/verigate
**Objective:** complete the Arc Mainnet authority integration and harden Verigate's authority boundary before claiming production-grade agent control.

## Executive decision

Verigate is an authority-control plane, not a global wallet firewall. It can enforce policy only where every consequential side effect is forced through a trusted execution boundary. A compromised agent, host, issuer key, executor, wallet or alternate tool path can defeat controls that exist only in the Verigate API/client.

The Arc Registry currently records and consumes signed authorization state. It does not escrow USDC, execute the payment, or prevent a wallet from sending a direct transfer outside the integrated Verigate path. Do not claim otherwise.

## Latency and finality: a necessary distinction

Arc advertises deterministic finality in less than one second. Verigate cannot truthfully promise that a transaction is finally settled faster than the chain that settles it. The product target is instead:

- Authorization latency: target p95 below 100 ms for warmed, local policy/identity/capability/signature evaluation, measured on a declared test environment.
- Pre-broadcast authorization workflow: target p95 below 500 ms excluding user approval, wallet signing, RPC inclusion and Arc consensus finality; measure each stage separately.
- Settlement finality: inherit Arc's protocol finality and report it only after the required Arc evidence is available.
- Never label an API response, optimistic receipt, or wallet prompt as transaction finality. Never claim "faster than Arc finality."

These are targets, not achieved measurements. Add reproducible benchmarks and report p50/p95/p99, hardware, concurrency, RPC region and sample count.

## Repository integration snapshot (2026-11-11)

- main contains the existing generic Arc network/payment adapter, but not the complete Registry lifecycle described below.
- PR #38 (integration/arc-authority) contains the Registry flow, 30 commits ahead and 40 behind main at the last comparison; GitHub reports it is not mergeable. Do not merge that divergent branch blindly.
- PR #40 (hardening/release-readiness) contains secure Docker defaults and a container CI job, but is also stale/diverged (1 commit ahead, 35 behind at last comparison).
- PR #41 (fix/arc-expired-confirmation-regression) adds a late-confirmation regression and evidence corrections on top of the Arc branch.
- PR #42 (feat/external-agent-integration-kit) adds the generic external-agent SDK/enrollment kit on top of the Arc branch.
- Consolidation branch: release/arc-security-consolidation-2026-11-11, created from current main. It is the safe integration workspace; do not overwrite main or force-push.
- Existing PRs remain open and are not merged by this checkpoint.

## Arc implementation present on the Arc branch (not yet integrated into main)

- Signed Arc payment ActionIntent bound to sender, recipient, token, amount, chain and transfer calldata.
- Identity, capability and deterministic policy validation before issuance.
- Arc Authority Registry registration and one-time consumption.
- Generic execution-consume route rejects Arc authorization to prevent bypass of the dedicated sequence.
- Receipt, sender, destination, calldata, status, full event topic hash, Registry state, canonical block hash and block timestamp checks.
- Local one-time execution consumption occurs only after confirmed Registry consumption.
- Wallet signing and payment broadcast remain separate explicit user actions.
- Arc wallet SDK and external agent SDK/enrollment material exist on their respective branches.

**Evidence boundary:** Registry deployment at 0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D, chain ID 5042, deployment transaction 0xe85784e81ca0069410e8555961c8403fa02adc1361c7455657106afc96855ebb, block 30012679, owner 0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C is user-confirmed from prior work. This checkpoint does not claim a fresh independent RPC verification or a Verigate-authorized USDC settlement.

## Security findings and required controls

### P0 — fail-closed production entry points
- Require API authentication for every non-public route in production.
- Require agent-signed intents for every executable authorization path.
- Disable unsigned capability authorization in production.
- Docker image and Compose must require API keys, signed intents, and loopback-only port binding by default.
- Production startup must reject missing/weak configuration; local demo mode must be explicitly selected and clearly separated.
- Add CI that builds and runs the container and proves unauthenticated protected requests return 401.

### P0 — execution boundary and bypass resistance
- Enumerate every side-effecting adapter: EVM, Arc, HTTP, MCP, subprocess, filesystem, cloud APIs and custom handlers.
- Require a single trusted enforcement point for each adapter; fail closed if policy, verifier, nonce store or audit storage is unavailable.
- Bind authorization to exact action bytes/normalized fields, chain, account, destination, value, calldata, token, amount, nonce and expiry.
- Prevent generic consume or legacy endpoints from bypassing chain-specific gates.
- Explicitly document that a user-controlled wallet can still transact outside Verigate unless the wallet/account itself is constrained by an on-chain guard or policy-enforcing signer.

### P0 — adversarial security suite
Required negative tests:
1. Missing/invalid API key, malformed auth configuration, tenant header confusion.
2. Unsigned capability issuance and legacy endpoint bypass.
3. Cross-tenant identity/capability/key/database access.
4. Forged agent identity, replayed signature, changed intent fields and nonce races.
5. Issuer-key compromise simulation and issuer rotation/revocation behavior.
6. Changed Arc chain, token, sender, recipient, amount, calldata, value, executor, receipt, event topic and Registry storage.
7. RPC disagreement, stale block, reorg/finality uncertainty and forged receipt.
8. Direct alternate execution path and untrusted handler child side effects.
9. Crash after on-chain consume but before local consume; verify no payment is released and recovery requires a fresh authorization.
10. Rate-limit/DoS and resource-exhaustion checks.

### P1 — key and governance security
- Separate agent, issuer, Registry owner/governance, executor and wallet keys.
- Add documented rotation, revocation and emergency kill-switch procedures.
- Use multisig/timelock or equivalent controls for Registry owner and issuer management.
- Move production issuer signing behind KMS/HSM or a dedicated signing service; encrypted files alone do not protect a compromised running host.
- Add key access audit events and least-privilege process/user separation.

### P1 — Arc contract and RPC verification
- Pin the deployed runtime bytecode hash to a reproducible compiler artifact and verify it on-chain.
- Verify owner, enabled issuer set, executor, token/network configuration and contract address against an independently trusted manifest.
- Define Arc-specific finality semantics; verify the provider's finalized/canonical block guarantees. Use independent RPC cross-checks and/or a self-operated node for high-assurance mode.
- Add deterministic recovery semantics for on-chain consumed/local unconsumed authorizations.
- Keep Registry registration/consumption and USDC payment separate in evidence and UI.

### P1 — measurable performance
- Benchmark policy evaluation, signature verification, storage/nonce consumption, Arc RPC stages and end-to-end wallet flow separately.
- Establish p50/p95/p99 targets. Initial targets: local authority decision p95 below 100 ms; server-side pre-broadcast path p95 below 500 ms excluding user/wallet and chain finality.
- Do not compare authorization latency with consensus finality as if they were equivalent.
- Optimize only after measurement; do not weaken signature, policy, nonce or finality checks for latency.

### P2 — independent assurance
- Add an externally runnable red-team harness with deterministic attack cases and machine-readable results.
- Produce an evidence bundle containing source commit, CI run, benchmark environment, deployed bytecode hash, contract state, transaction receipts and verification output.
- Commission independent review before making production-grade or unhackable claims.

## Merge and release gates

1. Consolidate PR #38, #41 and #42 changes onto this branch using reviewed file-level reconciliation with current main. Do not merge their stale bases.
2. Port PR #40 security defaults without reverting newer main CI, Docker, Anna or docs changes.
3. Resolve API and test conflicts manually; preserve current main behavior and test contracts.
4. Implement bytecode pinning, finality policy, recovery tests and adversarial tests.
5. Run full CI on the exact consolidation head; inspect every job, not just the aggregate status.
6. Re-read the final diff for secrets, accidental demo exposure, destructive changes and unsupported claims.
7. Open one consolidated PR to main. Merge only after the exact head passes all required checks.
8. After merge, independently verify main SHA and workflow run. No server deployment, key rotation, Registry owner change, wallet transaction or payment broadcast is authorized by this plan.

## Claims we can make now

- Verigate implements cryptographic agent identity, signed action authorization, deterministic policy checks, one-time execution consumption and portable evidence verification.
- The Arc Registry deployment is user-confirmed; the Registry integration exists on a separate unmerged branch.
- The current design is non-custodial and returns the exact payment transaction for a separate wallet approval.
- The current system is not independently security-audited and is not a global firewall against out-of-band wallet actions.

## Claims we must not make yet

- Unhackable, cannot be bypassed, production-grade audited security.
- Verigate settles faster than Arc finality.
- Every agent action is controlled unless all tool and side-effect paths are technically confined.
- Live Verigate Arc payment until its own registration, consumption and payment transactions are independently verified.
