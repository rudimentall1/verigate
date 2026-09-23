# Verigate — Project Context

## Product

Verigate is the **Agent Authority Control Plane** for autonomous agents.

The core rule is simple: an AI agent can propose an action; Verigate establishes the authority under which that action may execute.

Verigate is not an agent framework, chatbot, generic risk dashboard, or standalone risk scorer. Its job is to govern consequential agent authority across the full path from identity and intent to authorization, execution, evidence and learning.

## Lifecycle

IDENTIFIED → PROPOSED → VERIFIED → SIMULATED → AUTHORIZED → EXECUTING → OBSERVED → PROVEN → LEARNED

The control path is:
AgentIdentity → Capability → ActionIntent → Policy + Context + Intelligence → Adversarial Verification → AuthorityDecision → ExecutionAuthorization → Execution → Observation → Evidence → Learning.

The current implementation already contains important pieces of this path: ActionIntent, cryptographic AgentIdentity, signed agent intents, Capability Registry with revocation, deterministic policy evaluation, signed DecisionReceipt, short-lived ExecutionAuthorization, action fingerprints, fail-closed execution adapters and signed ExecutionReceipt.

## Authority model

**AgentIdentity** is the cryptographic principal. Its Ed25519 public key is identified by a SHA-256 fingerprint, and the Identity Registry controls active/revoked status.

A consequential `ActionIntent` can be signed by the agent identity before Verigate evaluates it. The signature binds the exact normalized intent and identity ID; changing the action invalidates the proof.

A **Capability** represents programmable authority granted to an agent: action types, resource/target scope, limits, networks, counterparties, required controls and expiry. The **Capability Registry** is the source of truth for active capabilities and supports explicit revocation. An ExecutionAuthorization is a short-lived proof that one exact ActionIntent is permitted under that identity and capability.

Revocation applies to future authorization only. Already-issued authorization remains cryptographically bound to its capability ID, version and SHA-256 digest.

The authority graph is:
Organization / Principal → Agent → Identity → Capability → Delegated Capability → ActionIntent → Resource → Effect → Evidence.

Delegation is constrained: a child capability cannot exceed its parent in scope, limits, conditions or lifetime, and delegation requires the parent identity's cryptographic signature. Effective authority follows the entire ancestor chain; revoking a parent or delegator identity invalidates descendant authority for future decisions.

Risk, intelligence and adversarial analysis can inform an AuthorityDecision, but they must never bypass deterministic capability, delegation and execution controls.

## Security invariants

1. BLOCK means no authorization, no broadcast, no nonce consumption, and no side effect.
2. Only ALLOW can mint execution authority.
3. Authorization is short-lived, nonce-bound, and tied to the exact normalized action/fingerprint.
4. Agent-signed intent must verify against the registered cryptographic identity before canonical authority can be issued.
5. Capability scope and identity status are checked before authority issuance.
6. Revoked identities/capabilities cannot grant future authority.
7. A delegated capability cannot exceed its parent's scope, limits, conditions or lifetime.
8. Delegation requires the identity that owns the parent capability to sign the exact child capability definition.
9. Effective authority requires every ancestor capability and bound identity to remain active.
10. Tampering with an authorized action must fail at the execution boundary.
11. Decision receipts prove the decision but are not themselves execution permission.
12. Evidence must preserve identity → capability → delegation path → intent → authorization → execution linkage.

## Product boundary

The core is protocol-agnostic. Payment rails and chains are adapters. Hackathon-specific integrations live under adapters/ and hackathons/ and must not fork the core.

## Current focus

The current product focus is the universal authority core: cryptographic agent identity, capabilities, exact ActionIntent verification, deterministic policy, authorization, execution enforcement and evidence. RWA, payments, EVM, Solana and future MCP/API/cloud adapters must consume the same authority contracts rather than define the core.
