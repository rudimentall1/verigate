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

## Architecture quality review

- The advisory structural scan is defined in `.github/workflows/architecture-audit.yml` and documented in `docs/ARCHITECTURE-QUALITY.md`.
- The workflow uses a pinned `deslop-please` commit and pinned SCIP indexers; these are CI-only tools, not runtime dependencies.
- Treat findings as architecture signals that require source-level review. Do not mechanically move code or change protocol/public interfaces to silence diagnostics.
- Investigate confirmed issues at their architectural boundary. Preserve Verigate authorization, enforcement, replay, expiry, and fail-closed invariants.
- Do not create a blanket allowlist or use `--update-allow` without a reviewed, documented reason.
- This scan does not analyze Solidity and does not replace security review, contract tests, Python tests, Anna UI tests, or execution-evidence verification.

## Package dependency direction

- Keep `core` below `attest`, `enforcement`, and `application`: core domain/policy modules must not import those higher-level packages.
- `attest` owns signed receipt and execution-authorization issuance/verification, historical authority replay, outcome attestations, adversarial authorization checks, signed evidence-graph construction, and portable proof packaging/offline verification; it may depend on core domain primitives.
- `enforcement` owns execution gates, routers, chain/tool adapters, and effect verification; it may depend on core and attest.
- `application` owns composition roots and workflows that combine core policy/evaluation with attestation and enforcement, including `GuardrailEngine`, Genesis lifecycle, governed wallet enrollment, and signed external execution-submission ingestion.
- Do not put an application orchestrator or a verifier harness in `core` merely because it uses core types.
- The import direction is documented in `docs/ARCHITECTURE-DEPENDENCY-BOUNDARIES.md`; preserve the direction when adding new modules.
