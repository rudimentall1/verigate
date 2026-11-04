# Valta × Verigate — pilot and commercial plan

**Status date:** 2026-11-04  
**Owner:** Verigate  
**Purpose:** Convert the current technical interest from Valta into a bounded, testable pilot and an explicit commercial decision.

## 1. The value proposition

Valta already provides financial controls such as wallet limits, spend policies, proxy enforcement, freezes, and audit records. Verigate is not a replacement for those controls.

The proposed complement is an independent authority layer that answers a different question:

- **Verigate:** Is this agent authorized to perform this exact action, with this exact payload, under this capability and policy, and has the authorization already been consumed?
- **Valta:** Is this action permitted by the account's financial policy, balance, wallet state, and provider integration?

The intended sequence is:

`Agent → Verigate authorization → Valta financial controls → execution`

Either layer may deny the action. Verigate must not bypass, weaken, or duplicate Valta's financial policy.

## 2. Evidence we can show today

### Implemented

- A Valta Chat Completions adapter exists in the Verigate repository.
- The adapter binds the exact request body and Valta run ID to a signed action intent.
- Verigate checks the registered identity, capability, signature, policy, and exact request.
- Only ALLOW can produce an execution authorization.
- The execution router consumes the one-time authorization before the adapter forwards the request.
- The adapter is intentionally single-tenant for this pilot. It is not a public multi-tenant service.

### Deployment and live smoke test

On 2026-11-04, the isolated Gensyn2 service was active and its local health check returned OK. A live signed request received ALLOW, obtained and consumed the one-time authorization, and was forwarded through Valta to the upstream provider.

The upstream returned HTTP 429 `credit_balance_exhausted`. Therefore:

- Verigate authorization and the forwarding path were demonstrated.
- A successful model completion was **not** demonstrated.
- This is not evidence of a successful paid transaction or a production-ready integration.

The repository tests use a fake Valta client and cover authorization-path behavior, including ALLOW, DENY, REPLAY, and TAMPER. A live sandbox evaluation with Valta's own evidence is still outstanding.

### Current deployment limits

- Single tenant only.
- Loopback-bound service, not exposed as a public API.
- No per-tenant Valta virtual-key isolation.
- No completed MCP integration into Valta's repository.
- No independent security audit.
- No confirmed successful live model response because the upstream account had no API credits.

## 3. Proposed pilot: one execution boundary

The first pilot must target one execution boundary agreed with Valta. Three paths must not be conflated:

1. **Existing Chat Completions path:** the current Verigate adapter in front of Valta's OpenAI-compatible endpoint. This is the path already deployed and smoke-tested, but the successful upstream completion remains unverified. It gates model inference, not a wallet transfer.
2. **MCP wallet-transfer path:** the current Valta-MCP repository exposes `valta_transfer_funds`, which calls `POST /wallet/transfer` with `fromAgentId`, `toAgentId`, `amount`, and optional `description`. This is the clearest first target for demonstrating independent authorization before a financial side effect. It requires a new action schema, adapter, and tests. No transfer has been executed or claimed.
3. **MCP proxy path:** `valta_proxy_request` is a spend-gated outbound call to supported providers. This is a possible later target, but it is not the same as a wallet-to-wallet transfer.

Valta-MCP Issue #1 now asks maintainers whether `valta_transfer_funds` is the right first financial execution boundary and requests sandbox/test semantics. The existing Chat Completions adapter does not prove either MCP path.

## 4. Acceptance criteria

The pilot is complete only when the agreed target has reproducible evidence for all of the following:

| Case | Required observable result |
|---|---|
| ALLOW | Exact authorized action is forwarded once, after one-time authorization consumption. |
| DENY | Protected Valta operation is not called. No side effect occurs. |
| WARN | Protected operation is not called unless an explicit, separately designed approval flow is agreed. |
| REPLAY | Reusing a consumed authorization is rejected. |
| TAMPER | Changing any bound action field or payload is rejected before forwarding. |
| FAIL-CLOSED | Invalid response, expired authorization, or unavailable Verigate stops the operation before forwarding. |

The evidence package should include redacted request identifiers, intent/action fingerprints, decision and authorization identifiers, authorization-consumption outcome, adapter result, Valta-side receipt/log where available, test output, and limitations.

A model-provider success response is a separate criterion from successful Verigate authorization. Both must be reported independently.

## 5. Deliverables for a bounded pilot

1. One runnable adapter example for the target selected by Valta.
2. Automated ALLOW, DENY, WARN, REPLAY, TAMPER, and FAIL-CLOSED tests.
3. A reproducible setup and test procedure using sandbox or mock credentials.
4. A short engineering report with evidence, limitations, and a recommendation for production hardening.

No production funds, customer data, or uncapped model-provider spend should be required. Any billable live request must be explicitly approved and capped by the account owner.

## 6. Commercial options to discuss before expanding scope

### Option A — paid technical pilot

A fixed scope, fixed deliverables, agreed acceptance criteria, named technical contact, and an agreed fee and payment schedule. The fee and dates must be agreed in writing before substantial additional implementation work begins.

### Option B — integration partnership / revenue share

Valta's public partner program describes revenue sharing based on verified wallet activity, monthly payouts, technical support, sandbox access, and co-marketing. The actual percentage, attribution rules, eligible revenue, duration, and payout terms are not published on the page and must be agreed in writing.

This option makes sense if Valta expects Verigate to contribute distribution, adoption, or a reusable integration that brings measurable wallet activity. It should not be treated as payment for custom engineering unless that is explicitly agreed.

### Option C — combined arrangement

A paid initial pilot, followed by a revenue-share agreement if the integration is accepted and reaches agreed adoption milestones.

## 7. Questions for Valta

1. Which first boundary is highest-value for Valta: the existing Chat Completions route or a Verigate gate in Valta-MCP?
2. Can Valta provide a sandbox, a dedicated test account, or test credentials with a capped provider budget?
3. Who is the engineering owner for the pilot and what test/evidence format do they require?
4. Is Valta open to a paid pilot, a revenue-share partnership, or a combined arrangement?
5. For revenue share: what percentage, revenue definition, attribution mechanism, payout schedule, and term would apply?

## 8. Engagement rules

- Do not claim the integration is accepted by Valta until maintainers confirm it.
- Do not claim a successful live model call or financial transaction without a successful result and corresponding evidence.
- Do not build the MCP path before Valta confirms the target boundary and sandbox assumptions.
- Do not expand the pilot into multi-tenant production deployment without a separate security and secret-isolation design.
- Do not undertake substantial unpaid custom development based only on general interest.
- Keep Verigate's core protocol and authorization logic in the Verigate repository; partner-specific glue belongs in adapters.
- Publish a joint case study only after both parties approve the technical results and wording.

## 9. Current next action

The technical update and report links have been sent to Debo Jolaosho in the existing email thread. Valta-MCP Issue #1 records the proposed MCP execution-boundary integration and explicitly distinguishes it from the existing Chat Completions smoke test.

Wait for Valta to confirm the target boundary, sandbox route, and commercial model. Until then, preserve the working deployment and avoid additional billable upstream requests or broad unapproved implementation work.

Useful links:

- Verigate repository: https://github.com/rudimentall1/verigate
- Valta pilot implementation: https://github.com/rudimentall1/verigate/blob/main/docs/valta-pilot.md
- Valta deployment evidence: https://github.com/rudimentall1/verigate/blob/main/docs/valta-pilot-deployment.md
- Valta-MCP integration issue: https://github.com/Valta-hq/Valta-MCP/issues/1
- Valta Partner Program: https://www.valta.co/partners
