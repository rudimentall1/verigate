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

## Mandatory documentation and repository discovery rules

These rules are mandatory for every contributor and agent, including documentation-only and code changes:

1. **Inspect before starting.** Before planning or changing anything, inspect the repository structure, the relevant source files, existing tests, dependencies, and applicable documentation. Read `AGENTS.md`, `PROJECT_CONTEXT.md` (if present), relevant architecture/decision records, and the documentation closest to the affected area. Do not assume a generic project layout; verify the actual repository.
2. **Keep documentation in sync.** After every significant change, update the relevant documentation, including architecture/context, task status, decisions, setup, operational guidance, and examples where affected. Do not create duplicate context files when an authoritative equivalent already exists; record the actual documentation layout.
3. **Separate facts from assumptions.** Never present an unverified assumption, inferred state, planned work, or untested behavior as an established fact. Label uncertainty explicitly and support factual claims with code, test output, CI results, or reproducible evidence.
4. **Validate docs before finishing.** Before declaring a task complete, re-read the affected documentation and verify that it matches the resulting code, configuration, tests, commands, and current repository state. Check links, paths, version numbers, status statements, and examples where practical.
5. **Commit docs with the change.** Commit documentation updates in the same commit/PR as the code or configuration change they describe. Do not leave required documentation updates in a separate follow-up commit/PR. For a documentation-only task, commit the complete documentation change as its own focused change.

If a requested documentation file does not exist, first inspect the repository for its authoritative equivalent. Create a new file only when it adds distinct, maintainable value and does not duplicate existing documentation.

## Development workflow

For a small change: inspect → implement → test → review.

For a substantial product change:
`/grill-me` → `/to-spec` → `/to-tasks` → `/implement` → code-review + security-review.

Use the skills from `~/.agents/skills/` when the corresponding command is requested.

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
