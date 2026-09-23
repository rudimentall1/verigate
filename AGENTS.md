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

## Repository rules

- Read existing code and docs before changing architecture.
- Prefer existing seams and conventions over new abstractions.
- Do not rewrite working integrations without a concrete reason.
- Do not add dependencies unless they materially improve the product.
- Tests must verify observable behavior, especially security invariants.
- Never claim live execution was verified unless it was actually run and confirmed.
- Keep hackathon-specific code isolated under `hackathons/` or adapters.

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
