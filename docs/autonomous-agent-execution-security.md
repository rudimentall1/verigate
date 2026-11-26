# A Practical Security Boundary for Autonomous AI Agents

Autonomous agents are moving from answering questions to taking actions: calling APIs, changing cloud resources, invoking tools and moving funds. The central security question is not whether a model sounds confident. It is whether the agent has authority to perform the exact action it is about to execute.

This note is a practical security checklist for developers building agent systems in the @flop_labs ecosystem and elsewhere.

**Author DID:** `did:key:z6MkgySvRFfL1Vp2i7HRdRjqxMicDVKh888sMh8TcWYxCd62`

## 1. Identity is not permission

A DID or API credential identifies a principal. It does not, by itself, grant unlimited authority.

Keep these concepts separate:

- **Identity:** which agent or service is making the request?
- **Capability:** which actions, resources, destinations and limits may it use?
- **Authorization:** is this exact proposed action allowed now?
- **Execution:** did the system enforce that decision before the side effect?

A compromised agent should not be able to turn possession of its identity into broader permissions.

## 2. Authorize the exact action, not a vague intention

A policy such as “the agent may pay vendors” is too broad. The authorization input should bind the fields that matter to execution, for example:

- operation and network;
- destination or recipient;
- asset and amount;
- resource or tool identifier;
- expiry, nonce and relevant context.

Normalize the request once, then make the policy decision over that normalized representation. The execution adapter must receive the same action that was authorized. If the destination, amount, tool or endpoint changes after approval, reject it and require a new authorization.

## 3. Put the check at the execution boundary

A UI approval or an LLM-generated statement is not an enforcement mechanism. The component that performs the side effect must verify authorization immediately before acting.

A minimal flow is:

```text
Agent proposes action
        |
        v
Normalize exact action
        |
        v
Verify identity + capability + policy
        |
        +---- DENY ----> no side effect
        |
       ALLOW
        |
        v
Issue short-lived, one-time authorization
        |
        v
Execution adapter verifies and consumes it
        |
        v
Perform the exact authorized action
        |
        v
Record outcome and evidence
```

Fail closed on missing credentials, malformed requests, policy errors, expired permissions, replayed nonces and mismatched execution parameters. A timeout must not silently become an approval.

## 4. Make permissions narrow and revocable

Prefer capabilities with explicit scope:

- allowed operations and tool names;
- allowed destinations and networks;
- per-action and cumulative limits;
- expiry and rate limits;
- approval requirements for exceptional actions.

Use short-lived credentials where possible. Revoke compromised identities and capabilities. A new agent session should not inherit broader authority merely because it has the same display name.

## 5. Keep evidence of both the decision and the outcome

An audit record should let an independent reviewer reconstruct:

1. who proposed the action;
2. the exact normalized action;
3. which policy and capability versions applied;
4. the authorization decision and its expiry/nonce;
5. which execution adapter consumed the authorization;
6. what side effect was attempted and what outcome was observed.

Sign or hash-link records where appropriate, protect them from silent modification, and distinguish executor self-reports from independent confirmation. A signed claim is evidence of who made the claim; it is not automatically proof that the external event happened.

## 6. Be precise about the enforcement boundary

Checking the first tool invocation does not automatically control every effect that tool can create. A trusted handler might spawn a subprocess, invoke a second tool, run a Git hook or make another network request.

Document whether enforcement covers only the direct call or the full transitive execution graph. Do not claim sandboxing or complete containment unless the runtime actually enforces it.

## A minimum pre-release test

Before connecting an agent to valuable resources, test these cases against the real execution adapter:

| Test | Required result |
|---|---|
| Allowed action with exact parameters | Execute once |
| Destination or amount changed after authorization | Block |
| Reuse of the same authorization | Block |
| Expired authorization | Block |
| Missing or invalid agent signature | Block |
| Policy service unavailable | Block |
| Tool handler attempts an undeclared child action | Block or explicitly mark outside the enforcement scope |

The evidence should show both the decision and the side-effect count. “Denied” is not enough if the transaction or API call still went through.

## How Verigate approaches this boundary

Verigate is an open-source authority-control-plane implementation exploring this model: an agent proposes an exact action; identity, capability and deterministic policy are checked; a signed one-time authorization is enforced by an execution adapter; and evidence can be verified separately.

The repository is a runnable protocol implementation and demo, not a hosted multi-tenant service. Its documented enforcement scope is explicit: direct execution paths are covered by the adapter contract, while arbitrary child effects are not automatically contained. Developers should verify the current implementation and its limits before relying on it in production.

Repository: https://github.com/rudimentall1/verigate

---

This contribution is a developer security checklist, not a claim of an official integration with FLOP Labs or a guarantee of rewards. It is published in connection with the Technocore community and @flop_labs.
