# Grok Workspace Review — 2026-11-13

## Decision

The uploaded Grok workspace is a standalone browser-side prototype for a Verigate Authority desk. It is useful as a product review and interaction reference, but it is **not a production-ready implementation** and must not be copied into the Anna App or Verigate runtime.

The workspace contains a second TypeScript policy engine, browser-local Zustand state, local Ed25519 signing, a mock conformance runner, and an audit page. Importing it would create a parallel authority path and risk presenting local browser checks as production Verigate evidence.

## What is already present in Verigate

The prototype's strongest architectural observations are already reflected in the current Verigate/Anna source:

- **Model output is advisory.** Deterministic policy owns ALLOW/WARN/BLOCK. Advisory risk flags may make a decision stricter; the model cannot issue execution authority.
- **Decision Receipt and Execution Authorization are separate artifacts.** The latter is capability-bound and one-time; the wallet handoff passes through ExecutionRouter.
- **Wallet outcomes are recorded explicitly.** Anna supports signed outcome receipts for `REJECTED`, `ABORTED`, and `UNKNOWN`, with different validation rules. A rejection requires EIP-1193 error 4001; an abort is limited to an approved pre-wallet or router-response-unknown phase; an ambiguous wallet result remains UNKNOWN.
- **Outcome receipts are not chain proof.** They are installation-signed self-reports. They do not establish transaction inclusion, finality, or independent confirmation.
- **The test suite already covers important cases.** It checks missing Router consumption, forged outcome classifications, one-time App approvals, idempotent retries, conflicting receipts, and authorization-budget enforcement.

Relevant implementation:
- `anna/executas/verigate-authority/verigate_authority_plugin.py`
- `tests/test_anna_execution_authorization.py`
- `core/engine.py`
- `core/storage.py`
- `attest/receipt.py`

## Useful gap exposed by the prototype: budget reservation lifecycle

The prototype correctly notices a product problem: a user can authorize an action, the Router can consume its one-time permission, and the wallet can reject the request. The authorization still counts against the rolling 24-hour budget.

The current behavior is deliberate and documented: the counter is based on non-BLOCK policy authorization records, not chain-confirmed transfers. A wallet outcome receipt records what Anna observed, but it does not currently reverse the policy accounting entry.

This should not be fixed with a generic `refund()` or by treating every negative receipt as proof that no funds moved. That would create a budget-bypass path.

### Recommended accounting model

Separate three quantities instead of overloading one daily-spend number:

1. **Authorized exposure** — amount for which Verigate issued execution authority.
2. **Pending reservation** — authorized amount whose execution outcome is not yet safely resolved.
3. **Settled spend** — amount supported by the configured settlement evidence source.

Proposed transitions:

| Evidence | Reservation treatment |
|---|---|
| Authorization issued, not handed to Router | Reserved until expiry or explicit safe cancellation |
| Router consumed; wallet returns EIP-1193 4001 | Eligible for release after exact App-approved REJECTED receipt |
| Proven abort before wallet request | Eligible for release after exact App-approved ABORTED receipt |
| Wallet request result ambiguous (UNKNOWN) | Keep reserved; reconcile before release |
| Transaction hash recorded (SUBMITTED) | Keep reserved until chain reconciliation |
| Independent successful/failed chain receipt | Settle or release according to verified chain result and finality policy |

This is a design proposal, not implemented behavior. The trust model, race handling, replay protection, rolling-window semantics, and source of independent chain evidence must be specified before code changes.

### Required tests before implementation

- A reservation is created exactly once per authorization.
- A matching REJECTED receipt releases at most once.
- ABORTED releases only for an allowed phase and only when the wallet request did not start.
- UNKNOWN never releases a reservation.
- SUBMITTED never releases a reservation merely because a wallet self-report exists.
- A conflicting or replayed outcome cannot alter accounting.
- Concurrent authorizations cannot exceed the cap while reservations are pending.
- Reconciliation is idempotent and preserves an auditable before/after ledger.
- Rolling 24-hour calculations remain correct across boundary times and clock skew.

## What not to import

- Do not copy the prototype's TypeScript `policy.ts` as a second policy authority. It duplicates the Python policy and uses a separate, browser-local state model.
- Do not treat its browser Ed25519 probe as proof that the bundled Python Executa or Anna Cloud runtime works.
- Do not copy its conformance numbers as current release evidence. Its audit text references older App/Executa versions and older Console state.
- Do not claim the prototype's local ledger is shared, durable, multi-tenant, or chain-backed.
- Do not adopt its recommendation to expose a manual reserve-release button as a production fix.

## Product priority

The highest-value follow-up is not another dashboard. It is a formally specified, concurrency-safe authorization reservation ledger with evidence-driven release and settlement. This directly improves treasury safety, predictable spend limits, and buyer trust.

Until that work is implemented and tested, describe the existing 24-hour control as an **authorization budget**, not a settled-spend tracker. Keep the current fail-closed behavior.
