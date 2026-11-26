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

## Mandatory documentation and truthfulness rules

These rules apply to every task and every agent working in this repository:

1. **Inspect before work.** Before making changes, read the relevant project documentation and inspect the repository structure, existing implementation, tests, configuration and dependency conventions. For Anna work, also follow the Anna-specific release/runtime reading requirements below.
2. **Keep documentation synchronized.** After every significant code, behavior, architecture, configuration, workflow or release-process change, update the relevant documentation in the same change.
3. **Separate facts from assumptions.** Never record an inference, guess, plan, unverified test result, external-platform behavior or expected outcome as an established fact. Label assumptions and pending verification explicitly. Cite the source, commit, test or observation for material claims where practical.
4. **Verify docs before completion.** Before declaring a task complete, re-read the affected documentation and compare it with the resulting code, configuration, tests and actual verification results. Correct stale, contradictory or unsupported statements.
5. **Commit docs with the related change.** Documentation updates required by a code or configuration change must be included in the same logical commit/PR as that change. Do not leave required documentation as a follow-up task. A documentation-only policy or correction may use its own focused commit.

## Repository rules

- Read existing code and docs before changing architecture.
- Prefer existing seams and conventions over new abstractions.
- Do not rewrite working integrations without a concrete reason.
- Do not add dependencies unless they materially improve the product.
- Tests must verify observable behavior, especially security invariants.
- Never claim live execution was verified unless it was actually run and confirmed.
- Keep hackathon-specific code isolated under `hackathons/` or adapters.

## Anna release rule — mandatory

Before any Anna release work, read [`_docs/anna-release-checkpoint.md`](./_docs/anna-release-checkpoint.md).

Every Verigate release must update **both** Anna Developer Apps **851** and **382**, using their separate account credentials and their matching Executa identities/tool IDs. A push to only one account is incomplete. Verify the exact App ID and Executa tool ID before each Working Draft push, then verify both drafts after upload. Do not cut, submit for review, or publish immutable versions unless explicitly requested.

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
