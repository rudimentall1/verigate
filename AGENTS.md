# Verigate — Agent Instructions

## Mission
Verigate is the trust and security layer between autonomous AI-agent intent and real-world side effects.

Core principle: AI can propose an action; only Verigate decides whether the agent has the right to execute it.

## Architecture invariants

- Decision is not execution authority.
- BLOCK means no authorization, no broadcast, no nonce consumption, and no side effect.
- Only ALLOW may mint an ExecutionAuthorization.
- Authorization is short-lived, nonce-bound, and tied to the exact normalized action/fingerprint.
- Tampering with an authorized action must fail at the execution boundary.
- Execution-side enforcement is part of the product, not merely a UI/API decision.
- Signed DecisionReceipt is evidence of the decision; it is not permission to execute.
- Core authorization/policy logic remains protocol-agnostic. Integrations belong in adapters/hackathon packs.
- Do not fork Verigate for individual hackathons.

## Development workflow

For a small change: inspect → implement → test → review.

For a substantial product change:
`/grill-me` → `/to-spec` → `/to-tasks` → `/implement` → code-review + security-review.

Use the skills from `~/.agents/skills/` when the corresponding command is requested.

## Mandatory documentation and repository workflow

These rules apply before, during, and at the end of every task—not only architecture changes.

1. **Inspect before starting.** Read this file, the repository structure, the README, and all relevant project documentation before changing code or configuration. Inspect the relevant implementation, tests, dependency manifests/lockfiles, and current Git/PR state. Read `PROJECT_CONTEXT.md`, `TASKS.md`, and `DECISIONS.md` when they exist; do not assume a missing file exists or invent its contents.
2. **Keep facts separate from assumptions.** Do not record an inference, guess, plan, unverified report, or expected behavior as an established fact. Label it explicitly as an assumption, hypothesis, pending check, or proposed decision, and record the source and verification status where useful.
3. **Update documentation with significant changes.** When behavior, architecture, interfaces, dependencies, security boundaries, operational procedures, decisions, or task status materially change, update the owning documentation and the project checkpoint in the same change.
4. **Verify documentation before finishing.** Re-read the affected documentation and check it against the final code, tests, configuration, actual command output, current branch/commit/PR state, and known limitations. Remove or correct stale claims, unsupported success statements, outdated commands, and inconsistent references.
5. **Commit documentation with its corresponding implementation.** Documentation that describes or is required to understand a code/configuration change must be included in the same commit and PR as that change—not deferred to a later docs-only follow-up. A genuinely documentation-only task may use its own focused documentation commit/PR.

A task is not complete until the relevant documentation has been checked for accuracy and updated where required.

## Repository rules

- Read existing code and docs before changing architecture.
- Prefer existing seams and conventions over new abstractions.
- Do not rewrite working integrations without a concrete reason.
- Do not add dependencies unless they materially improve the product.
- Tests must verify observable behavior, especially security invariants.
- Never claim live execution was verified unless it was actually run and confirmed.
- Keep hackathon-specific code isolated under `hackathons/` or adapters.

## Anna live-runtime evidence — mandatory context

Before changing Anna, read:
- `anna/docs/RELEASE-STATUS.md`
- `anna/docs/history/SESSION-CHECKPOINT-2026-11-10-LIVE-METAMASK.md`
- `anna/docs/ANNA-PLATFORM-COMPATIBILITY-2026-11-10.md`

Use the platform compatibility review as the current source for schema-4, Executa, APS, Agent Session and `tools.invoke` failure semantics. Do not copy legacy host API declarations from older Anna tutorials into a schema-4 App.

The 9 November 2026 user-supplied recording proves a real Brave + MetaMask EIP-1193 wallet hand-off for 25 USDC on Base. Verigate issued and verified a one-time ExecutionAuthorization; ExecutionRouter consumed it before the real MetaMask signature prompt. The user denied the MetaMask signature, and Anna displayed `MetaMask Tx Signature: User denied transaction signature.`

This is a successful live wallet hand-off / Router-consumption negative-path test. It is **not** a successful payment: no returned transaction hash, broadcast or on-chain settlement is shown. The exact immutable App version is not visible in the recording.

Never repeat the false claim that no wallet was connected or that MetaMask hand-off was never tested. Never inflate the recording into a successful payment. Distinguish it from automated tests that use a mocked EIP-1193 provider. The 10 November in-App cancellation recording is a separate test.

## Verification priorities

When touching authorization/enforcement, verify:
1. ALLOW → authorization → execution → real side effect/evidence.
2. BLOCK → no authorization → no broadcast → no side effect.
3. Replay is rejected.
4. Tampered intent/calldata/destination is rejected.
5. Expired authorization is rejected.

## Git

- Keep commits focused and descriptive.
- Inspect git status/diff before committing.
- Never discard unrelated user changes.
