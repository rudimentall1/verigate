# Verigate Security and Arc Completion Plan

**Updated:** 2026-11-11
**Repository:** rudimentall1/verigate
**Objective:** complete the Arc Mainnet authority integration and harden Verigate's authority boundary before claiming production-grade agent control.

## Executive decision

## Implementation status in main (2026-11-11)

Merged to main:
- PR #53: Arc Authority Registry lifecycle, external Agent SDK/enrollment, wallet client, finalized-block verification, runtime bytecode hash enforcement, issuer check, API default-deny, signed-intent enforcement, production Docker defaults and container CI.
- PR #54: WebView-safe Anna confirmation overlay and updated E2E harness.
- Exact PR #53 head passed all four CI jobs in run #42995150968.
- Exact PR #54 head passed all four CI jobs in run #42999094385, including Anna UI E2E and Linux Executa build/smoke.
- PRs #38, #40, #41 and #42 were reconciled into #53 and closed as superseded. PR #53 is merged as 1889963944756e271c968542bdf750c272c0c874.
- PR #54 is merged as 6ab3a289c300cb6d614d27bb7134ae251f7db261.

Not independently completed:
- The live Arc deployment verification script has not been run. Runtime hash is not yet independently confirmed or configured in the target service environment.
- A separate post-merge main CI result after the squash commits has not yet been verified.
- On-chain-consumed/local-failure recovery, KMS/HSM, complete key rotation, multisig governance, full adapter confinement, load/DoS tests, independent penetration test and a live Verigate-authorized USDC payment remain open.



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

- main now contains the Arc Authority Registry lifecycle and production API/container hardening from merged PR #53.
- main also contains the Anna WebView-safe confirmation overlay from merged PR #54.
- PR #38, #40, #41 and #42 are closed as superseded by #53.
- PR #53 is merged. PR #54 is merged.
- PR #37 was reviewed and closed as a historical server snapshot: its distinct Valta, governance, evidence, tenancy and authority-graph modules were byte-for-byte identical to main; its API/schema/storage/engine versions were older. Backup files and generated contract build artifacts were not ported.
- PR #16 was reviewed and closed as superseded by newer/equivalent Anna code already in main. Its real Anna Cloud Agent acceptance and durable Cloud persistence gates remain unverified.
- PR #18 was closed because its content[].text JSON-envelope fix is already present in main. PR #19 was closed after its overlay change was ported and merged through #54.
- Four open PRs remain: #28 Anna release checkpoint, #25 Guardian-specific bootstrap, #14 Render deployment runbook and #13 PortalDot Substrate one-time consumption.



## Arc implementation now present in main

- Signed Arc payment ActionIntent bound to sender, recipient, token, amount, chain and transfer calldata.
- Identity, capability and deterministic policy validation before issuance.
- Arc Authority Registry registration and one-time consumption lifecycle.
- Generic execution-consume route rejects Arc authorization to prevent bypass of the dedicated sequence.
- Receipt, sender, destination, calldata, status, full event topic hash, Registry state, canonical block hash, finalized-head and block timestamp checks.
- Local one-time execution consumption occurs only after confirmed Registry consumption.
- Runtime bytecode pinning requires VERIGATE_ARC_REGISTRY_CODE_HASH; missing or mismatched hash fails closed.
- Configured executor must be the Registry owner and an enabled issuer.
- Wallet signing and payment broadcast remain separate explicit user actions.
- External agent SDK, public enrollment package, operator enrollment/revocation script and HTTP client are in main.

**Evidence boundary:** Registry deployment at 0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D, chain ID 5042, deployment transaction 0xe85784e81ca0069410e8555961c8403fa02adc1361c7455657106afc96855ebb, block 30012679, owner 0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C is user-confirmed from prior work. This plan does not claim fresh independent RPC verification or a Verigate-authorized USDC settlement.



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

## Completion and release gates

1. Verify the post-merge main CI run. The PR source heads passed CI, but this does not replace a separately verified post-merge run.
2. Run `npm run verify:arc-deployment` against Arc Mainnet using read-only RPC access. Record chain ID, deployed runtime hash, owner, enabled issuer and finalized head.
3. Independently compare the deployed runtime hash with the reviewed source/compiler output. Configure VERIGATE_ARC_REGISTRY_CODE_HASH in the target service environment only after verification and explicit operational approval.
4. Add recovery tests for on-chain Registry consumption followed by local persistence failure. Define reconciliation/recovery without releasing payment authority on ambiguous state.
5. Add adversarial API tests for tenant confusion, unsigned capability, replay/race, identity tampering and direct execution bypass.
6. Benchmark p50/p95/p99 for local authorization and server pre-broadcast stages. Include environment, concurrency and sample count; do not weaken security checks to meet targets.
7. Complete load/DoS testing, KMS/HSM or isolated signer design, key rotation/emergency revocation and Registry multisig/timelock governance.
8. Obtain independent security review before production-grade assurance claims.
9. Perform a live Verigate registration/consumption flow only with explicit operational approval. Any USDC payment broadcast requires separate explicit approval.

No production server deployment/restart, key rotation, Registry owner change, wallet transaction or payment broadcast is authorized by this plan.



## Claims we can make now

- Verigate implements cryptographic agent identity, signed action authorization, deterministic policy checks, one-time execution consumption and portable evidence verification.
- The Arc Authority Registry integration and its verification lifecycle are merged into main.
- The Registry deployment details are user-confirmed historical evidence; fresh read-only Mainnet verification is still pending.
- The current design is non-custodial: the integrated client prepares the Registry and payment transactions for separate wallet approval.
- API production defaults now fail closed and the container CI validates authentication behavior.
- The Anna confirmation UI uses a WebView-safe overlay; the updated exact-head CI passed.



## Claims we must not make yet

- Unhackable, cannot be bypassed, production-grade audited security.
- Verigate settles faster than Arc finality.
- Every agent action is controlled unless all tool and side-effect paths are technically confined.
- Operational runtime-bytecode pinning until the actual Mainnet runtime hash is independently verified and configured.
- Live Verigate Arc payment until its own registration, consumption and payment transactions are independently verified.
- Real Anna Cloud Agent acceptance or durable Cloud persistence until those lifecycle tests are completed.
