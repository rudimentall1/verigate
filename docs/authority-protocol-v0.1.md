# Verigate Authority Protocol v0.1

## Purpose

Genesis 2.0 makes **Authority** the first-class control-plane object.

Verigate does not grant an agent arbitrary permission because an action looks safe. It resolves whether the agent can perform that exact consequential action under an existing identity, capability, policy and dynamic authority state, then produces execution authority that can be enforced and proved.

The protocol is intentionally independent of payment rails and blockchains.

## Canonical lifecycle

IDENTIFY → PROPOSE → VERIFY → DECIDE → AUTHORIZE → ENFORCE → OBSERVE → PROVE → LEARN

| Stage | Canonical object | Question |
|---|---|---|
| IDENTIFY | AgentIdentity | Who is acting? |
| PROPOSE | ActionIntent / Intent Graph | What does the agent propose? |
| VERIFY | Identity + Capability + context | Is the request authentic and in scope? |
| DECIDE | Policy + AuthorityDecision | Is the exact action permitted? |
| AUTHORIZE | ExecutionAuthorization | What exact action may execute, once? |
| ENFORCE | Execution Fabric | Can the executor prevent drift/replay? |
| OBSERVE | ExecutionReceipt / Outcome | What actually happened? |
| PROVE | Evidence / Attestation / Proof | Can a third party verify it? |
| LEARN | AuthorityTransition | Should future authority change? |

## Canonical objects

### AgentIdentity

Cryptographic principal representing the agent. Existing Ed25519 identity registration and revocation remain the implementation source of truth.

### Capability

Static, programmable ceiling over actions, targets/resources, networks/assets, limits, conditions and lifetime. Delegation can only narrow the parent scope.

### Authority

The current effective authority envelope. It references the exact identity and capability versions rather than duplicating their permission state.

Dynamic authority states:

- PROBATION
- LIMITED
- STANDARD
- ELEVATED
- SUSPENDED

**Invariant:** dynamic authority can never widen the static capability ceiling. A multiplier above 1.0 is invalid.

### ActionIntent

Canonical description of one consequential action. Payments are only one adapter; MCP tools, APIs, cloud/database operations and contract calls use the same intent boundary.

### AuthorityRequest

A protocol-level request referencing an exact intent and identity. A request is **not permission**. Permission exists only after policy, capability and authority verification produce an ExecutionAuthorization.

### ExecutionAuthorization

Short-lived, nonce-bound, exact-action execution authority. Existing execution adapters consume this artifact fail-closed.

### Evidence

Hash-addressed provenance connecting identity, delegation, policy, decision, authorization, execution, observation and attestation.

### AuthorityTransition

Evidence-bearing change to dynamic authority. External/chain verification, not executor self-report, is the basis for automatic authority changes.

## Non-negotiable invariants

1. **AI does not mint its own authority.**
2. **A request is not an authorization.**
3. **Dynamic authority never exceeds static capability.**
4. **Authorization is bound to the exact intent.**
5. **Execution must fail closed on replay or action drift.**
6. **Observation is not automatically truth; trusted attestation is required for automatic authority updates.**
7. **Proof must be independently verifiable without trusting the Verigate runtime.**
8. **Blockchain/payment integrations are execution adapters, not the product boundary.**

## Migration strategy

Genesis 2.0 is an architectural layer over the existing implementation.

- core.identity remains the identity registry.
- core.capabilities remains the capability source of truth.
- core.authority remains the delegation graph.
- core.authority_state remains the dynamic authority engine.
- core.authorization remains the execution-authority minting path.
- core.evidence remains the provenance graph.
- core.outcome remains the independent outcome/attestation plane.
- core.adversarial remains the mutation-based verification plane.

core.authority_protocol provides the canonical vocabulary and immutable envelopes that allow those proven primitives to converge without a rewrite.

## Next protocol boundary

The next Genesis milestone is **Intent Graph v0.1**:

Goal → Intent → Sub-intent → Action → Dependency → Consequence

This should make a multi-step agent plan addressable as one authority graph while preserving exact execution authorization at each side-effect boundary.
