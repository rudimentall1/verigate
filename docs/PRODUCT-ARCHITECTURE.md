# Product architecture: human delegation, agent authority, controlled execution

Verigate is infrastructure for authorizing actions performed by AI agents and other automated systems. Anna is the first user-facing integration. These are complementary roles, not competing product definitions.

## The roles

- **Human or organization:** defines the authority to delegate, sets limits, approves sensitive actions where required, and can revoke permissions.
- **Anna:** provides a human-facing control interface for expressing payment intent and taking explicit approval steps. Anna does not make the security decision and does not grant authority on its own.
- **AI agent or application:** proposes an action and supplies the exact action details. The agent is not trusted to decide whether its own request is permitted.
- **Verigate:** independently evaluates identity, delegated authority, capabilities, policy and relevant context. It issues a signed, action-bound, one-time authorization only when the request is permitted.
- **Execution adapter:** enforces the authorization at the execution boundary before causing the side effect.
- **External verifier:** can inspect the portable evidence using the issuer's public key without trusting the original runtime.

## Reference flow

```text
HUMAN / ORGANIZATION
        |
        v
ANNA — HUMAN CONTROL INTERFACE (first integration)
        |
        | delegated intent / explicit approval when required
        v
VERIGATE — AUTHORITY & AUTHORIZATION LAYER
        |
        +-- identity and delegated authority
        +-- capabilities and deterministic policy
        +-- contextual risk signals and evidence
        +-- signed, action-bound, one-time authorization
        +-- revocation and execution controls
        |
        v
AI AGENT / APPLICATION
        |
        | exact proposed action + authorization
        v
EXECUTION ADAPTER / ENFORCEMENT BOUNDARY
        |
        v
BLOCKCHAIN / PAYMENT NETWORK / BUSINESS SYSTEM
        |
        v
EXECUTION EVIDENCE -> PORTABLE VERIFIABLE PROOF
```

The agent may also integrate directly with Verigate through its API or SDK. Anna is not a required dependency, a privileged security bypass, or the only way to use the protocol.

## Security boundary

Anna's AI model can help interpret a request and provide advisory context. It cannot override deterministic policy, issue execution authority, or turn a BLOCK into an approval. Human confirmation is a separate control where the integration requires it; it is not a substitute for Verigate's policy and cryptographic authorization.

An authorization is meaningful only when the relevant executor checks it through the supported enforcement boundary. Actions that bypass that boundary are outside the guarantee. Verigate must not claim to control arbitrary downstream or transitive effects unless the adapter explicitly enforces them.

## Product and commercial boundary

Verigate is the core developer and infrastructure product: protocol, API, SDK, policy evaluation, signed authorization, enforcement integration and portable evidence. Its intended buyers are teams building or operating agents and systems that can move money or perform privileged actions.

Anna is the first human-facing control interface and a reference integration. It demonstrates how a person can delegate bounded authority to an agent and review sensitive actions. It can later be distributed independently, but it is not a separate AI-wallet thesis and should not pull the roadmap toward a generic assistant or wallet.

The product can be integrated without Anna. The human or organization remains the source of delegated authority; the agent remains the proposer of actions; Verigate remains the independent authority decision and enforcement layer.

## What this document does not claim

This is the intended product and trust architecture, not a claim that every deployment mode is production-ready. Current limitations, supported execution paths and evidence status are documented in the repository's current-state and threat-model documentation. Each integration must state which execution boundary it actually enforces.
