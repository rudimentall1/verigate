# Verigate — integration partner brief

**Version date:** 2026-11-04  
**Repository:** https://github.com/rudimentall1/verigate

## What Verigate adds

Verigate is an independent authorization and execution-control layer for autonomous agents.

Wallet providers already have important controls: budgets, transaction caps, allowlists, human approvals, key isolation, and compliance screening. Verigate is designed to complement those controls, not replace them.

The partner-facing question is:

**Before this agent triggers this exact external action, can the execution boundary verify a short-lived, single-use authorization that is cryptographically bound to the agent, capability, policy, and exact action payload?**

Verigate can sit immediately before an existing execution operation. The partner's own controls still run afterward and remain authoritative for its wallet, funds, provider credentials, compliance checks, and settlement.

## Execution model

1. An agent proposes an action.
2. The integration constructs a deterministic action intent from the exact operation and payload.
3. The agent identity signs the intent.
4. Verigate checks identity, capability, policy, signature, and the exact action fingerprint.
5. Only ALLOW can issue an execution authorization.
6. The execution boundary verifies and consumes the one-time authorization.
7. The partner's existing financial/risk controls evaluate the action.
8. The action proceeds only if both systems allow it.

DENY, WARN, invalid or expired authorization, replay, payload tampering, and Verigate unavailability must stop the protected operation. The exact adapter contract and action schema are agreed with each partner.

## What stays with the partner

Verigate does not replace or claim to provide:

- custody, key management, wallet balances, or settlement;
- KYC/KYT, sanctions screening, fraud decisions, or regulatory compliance;
- the partner's spend policy, wallet limits, or transaction simulation;
- provider-specific credential management;
- a guarantee that an external network or provider will successfully complete an allowed action.

The partner remains responsible for its existing financial and operational controls.

## Where this can fit

Potential integration surfaces include:

- agent wallet and programmable wallet SDKs;
- payment and payout APIs;
- MCP servers that expose financial tools;
- agent execution frameworks and tool routers;
- x402 and other machine-payment execution boundaries.

A first pilot should protect one narrowly defined operation, not attempt to wrap every endpoint at once.

## Pilot package

A bounded pilot should include:

1. One runnable adapter integrated at an agreed execution boundary.
2. A deterministic action schema binding all fields that affect the side effect.
3. Automated ALLOW, DENY, WARN, REPLAY, TAMPER, expiry, and dependency-failure tests.
4. Evidence that denied or invalid actions never invoke the protected operation.
5. A reproducible setup and test procedure using mocks or partner sandbox credentials.
6. A short engineering report with evidence, limitations, and production-hardening requirements.

No production funds or customer data are required for the mocked security suite. Any live, billable request must be separately approved and capped by the account owner.

## Commercial models

We are open to one of three structures:

- **Paid technical pilot:** fixed scope, deliverables, acceptance criteria, payment milestones, and named engineering owner.
- **Integration partnership:** revenue share tied to clearly defined and attributable customer or wallet activity, with written rate, attribution, reporting, payout, and term.
- **Combined:** paid implementation followed by revenue share or a support agreement after acceptance.

We do not treat an unspecified future revenue share as payment for substantial custom engineering. Scope and compensation must be agreed before expanding the work.

## Current evidence and limits

The Verigate repository contains a Valta Chat Completions adapter and automated tests using a fake Valta client. The adapter binds the exact request body and Valta run ID, requires signed intent and a registered capability, and consumes a one-time execution authorization before forwarding.

On 2026-11-04, the isolated Valta pilot service on Gensyn2 was active. A live signed request received ALLOW, and its execution authorization was issued and consumed before forwarding through Valta. The upstream returned HTTP 429 `credit_balance_exhausted`. Successful model completion was therefore **not demonstrated**.

The current Valta deployment is single-tenant and loopback-only. It is not a production multi-tenant service. The Valta MCP integration is proposed but has not been implemented or accepted by Valta.

Evidence:
- Valta pilot scope: https://github.com/rudimentall1/verigate/blob/main/docs/valta-pilot.md
- Valta deployment record: https://github.com/rudimentall1/verigate/blob/main/docs/valta-pilot-deployment.md
- Valta pilot and commercial plan: https://github.com/rudimentall1/verigate/blob/main/docs/valta-partner-pilot-commercial-plan.md

## Initial partner research

These are research targets, not existing partnerships or endorsements:

- **Circle Agent Stack** — agent wallets and machine-initiated transactions with user-defined spending policies and wallet-level controls. Potential fit: an additional independent authority check at the action boundary. https://www.circle.com/agent-stack
- **Coinbase Developer Platform Agentic Wallets** — agent wallet infrastructure with Smart Guardrails, session/transaction caps, and enclave isolation. Potential fit: identity- and action-bound authorization with separate execution evidence. https://www.coinbase.com/developer-platform/products/agentic-wallets
- **Crossmint Agentic Payments** — agent wallets, stablecoin infrastructure, spending caps, merchant allowlists, and human-approval options. Potential fit: independent authorization for exact actions across provider integrations. https://www.crossmint.com/solutions/agentic-payments

Each target needs its own technical discovery. Existing provider controls may already cover much of the use case; a pilot is justified only if the team values an independent, provider-neutral authorization boundary and its evidence.

## Proposed first conversation

We ask the engineering/product owner to identify one operation where an independent authorization check would materially reduce risk, provide a sandbox or mocked integration contract, and agree whether the pilot is paid, partnership-based, or combined before substantial implementation begins.
