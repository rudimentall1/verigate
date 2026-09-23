# Verigate — Project Context

## Product

Verigate is the trust and security layer between autonomous AI-agent intent and real-world side effects.

The core rule is simple: AI can propose an action; only Verigate decides whether the agent has the right to execute it.

Verigate is not an agent framework, chatbot, generic risk dashboard, or risk scorer. Its primary job is authorization and execution enforcement.

## Lifecycle

Discover → Authorize → Enforce → Prove → Learn

The execution security path is:
AI Agent → ActionIntent → identity/intent checks → deterministic policy → risk/intelligence/simulation/evidence → ALLOW/WARN/BLOCK → signed authorization → execution-side enforcement → real side effect → audit/evidence.

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
