# Verigate — Project Context

## Product

Verigate is the **Agent Authority Control Plane** for autonomous agents.

The core rule is simple: an AI agent can propose an action; Verigate establishes the authority under which that action may execute.

Verigate is not an agent framework, chatbot, generic risk dashboard, or standalone risk scorer. Its job is to govern consequential agent authority across the full path from identity and intent to authorization, execution, evidence and learning.

## Lifecycle

IDENTIFIED → PROPOSED → VERIFIED → SIMULATED → AUTHORIZED → EXECUTING → OBSERVED → PROVEN → LEARNED

The control path is:
AgentIdentity → Capability → ActionIntent → Policy + Context + Intelligence → Adversarial Verification → AuthorityDecision → ExecutionAuthorization → Execution → Observation → Evidence → Learning.

The current implementation already contains important pieces of this path: ActionIntent, deterministic policy evaluation, signed DecisionReceipt, short-lived ExecutionAuthorization, action fingerprints, fail-closed execution adapters and signed ExecutionReceipt.

## Authority model

A **Capability** represents programmable authority granted to an agent: action types, resource/target scope, limits, networks, counterparties, required controls and expiry. An ExecutionAuthorization is a short-lived proof that one exact ActionIntent is permitted under that authority.

The core graph is:
Agent → Capability → ActionIntent → Resource → Effect → Evidence.

Risk, intelligence and adversarial analysis can inform an AuthorityDecision, but they must never bypass deterministic capability and execution controls.

## Security invariants

1. BLOCK means no authorization, no broadcast, no nonce consumption, and no side effect.
2. Only ALLOW can mint execution authority.
3. Authorization is short-lived, nonce-bound, and tied to the exact normalized action/fingerprint.
4. Tampering with an authorized action must fail at the execution boundary.
5. Decision receipts prove the decision but are not themselves execution permission.

## Product boundary

The core is protocol-agnostic. Payment rails and chains are adapters. Hackathon-specific integrations live under adapters/ and hackathons/ and must not fork the core.

## Current focus

The current submission-critical integration is CoinMarketCap RWA, with Solana Devnet providing a real execution proof. The product should demonstrate both the decision and the enforcement boundary.
