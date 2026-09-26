# Verigate

**Agent Authority Control Plane / Agent Authority Infrastructure for autonomous agents.**

AI agents can propose consequential actions. Verigate decides whether the agent has the authority to execute the exact action, enforces that authorization at the execution boundary, records what happened, and produces evidence that can be verified independently later.

> **AI may propose an action; only Verigate decides whether the agent has the authority to execute it.**

The product boundary is not a wallet, risk score, policy dashboard, blockchain guard, or agent framework. Payments, EVM, Solana, HTTP and MCP are execution adapters around one protocol-agnostic authority model.

```text
AGENT
  ↓
ACTION INTENT
  ↓
IDENTITY + CAPABILITIES + CONTEXT + POLICY
  ↓
AUTHORITY DECISION
  ↓
SIGNED EXECUTION AUTHORIZATION
  ↓
EXECUTION-SIDE ENFORCEMENT
  ↓
REAL SIDE EFFECT
  ↓
OBSERVATION + OUTCOME ATTESTATION
  ↓
EVIDENCE + AUTHORITY UPDATE
  ↓
PORTABLE PROOF
  ↓
ANY THIRD PARTY → VALID / INVALID
```

## The judge-level proof

The strongest Verigate demonstration is not an ALLOW/BLOCK screen. It is the complete lifecycle:

```text
Give Verigate an agent action.
        ↓
Verigate decides authority.
        ↓
Execution produces evidence.
        ↓
The proof leaves the runtime.
        ↓
Anyone can verify that evidence without trusting Verigate.
        ↓
Change the evidence.
        ↓
Independent verification returns INVALID.
```

Genesis 2.0 is executable locally:

```bash
python examples/genesis_demo.py
```

It runs the real lifecycle contract, verifies the checked-in portable proof with the standalone verifier, then mutates the proof and requires independent rejection.

## Why Verigate

Autonomous agents increasingly need to call APIs, use MCP tools, modify cloud resources, write data, move money, execute contracts, and trigger other irreversible operations. The hard problem is not merely deciding whether an action looks risky. It is proving that the principal had authority for **this exact action**, that the execution boundary enforced that authority, and that the resulting evidence was not rewritten afterward.

Verigate makes **authority** a first-class protocol object: identity, capabilities, delegation, constraints, policy, context, time, budget, dynamic state, revocation and history combine into an authorization decision. Dynamic authority can change from verified outcomes, but never beyond the static capability ceiling.

---

## Current state

This repository contains a runnable Genesis 2.0 authority lifecycle and its verification boundaries. It is a protocol implementation/demo, not a hosted multi-tenant service. Specifically:

| Component | Status |
|---|---|
| Policy engine (caps, allowlists, rate limits, new-payee/daily limits) | **Real.** Deterministic rules, no statistical "risk scores." Covered by the full automated suite. |
| Ed25519 signing + independent verification | **Real.** Standard `cryptography` library primitives, not a custom crypto scheme. Tampering is detected, not just claimed. |
| x402 header parsing | **Real**, for the `exact` scheme with `extra.name` asset identification. Refuses to guess decimals for an unrecognized asset/network pair rather than silently misjudging an amount — extend `x402/parser.py:_KNOWN_DECIMALS` as you verify more pairs. |
| Audit log / rate limiting / daily-spend tracking | **Real**, SQLite-backed, single-process. For multiple replicas, point every process at shared storage or swap in a real database — the `Storage` interface is small. |
| FastAPI HTTP layer | **Written**, not yet load-tested or deployed. Runs with `uvicorn api.main:app`. |
| AP2 / other payment-rail adapters | **Not built.** The architecture reserves the seam (`core.models.PaymentIntent` is rail-agnostic) but only x402 has a working parser today. |
| Agent Identity Registry | **Real.** Ed25519 identities are registered by public-key fingerprint, can be revoked, and can sign exact `ActionIntent` envelopes before authorization. |
| Capability Registry | **Real.** Capabilities are persistent, scoped, versioned and revocable; authority artifacts bind capability ID/version/digest. |
| Dynamic Agent Authority | **Real.** Verified execution outcomes deterministically promote/demote effective authority inside the static capability ceiling; snapshots are persisted and bound to execution authorization. |
| Adversarial Verification Plane | **Real.** A reusable mutation corpus challenges signed execution authority and exposes the result through an independent verification endpoint. |
| Signed Policy Versions | **Real.** Policy identity, version, exact digest and provenance are signed and bound into decision, authorization and execution evidence. |
| Governed Policy Publication | **Real.** A policy version can be published into the governed registry only after an exact-action quorum with role separation; strict engines reject unapproved policy versions. |
| Policy Freeze / Rollback | **Real.** Governance can freeze a governed policy immediately or activate a previously governed digest; strict runtimes enforce the control state on every authority issuance and persist control actions against replay. |
| Governance / Authority Reset | **Real.** SUSPENDED authority can only enter a new epoch through a signed governance action; static capability revocation remains final. Single-governor compatibility exists, and the hardened path supports configurable multi-party quorum and role separation. |
| Authorization service | **Real.** Generic `ActionIntent` decisions can mint the same portable receipt and one-time authority used by payment and other execution flows. |
| Execution enforcement boundary | **Real.** One-time signed capabilities are consumed fail-closed; the local and dependency-light EVM adapters share the same gate. |
| Multi-tenant / hosted key management | **Not built.** Today, one issuer keypair per deployment, loaded from a local file. |

---

## Quickstart

```bash
pip install -r requirements.txt

# Run the full automated suite
PYTHONPATH=. python3 -m unittest discover -s tests -v

# Run the Genesis 2.0 judge-grade lifecycle + portable proof + tamper demo
PYTHONPATH=. python3 examples/genesis_demo.py

# Legacy payment / attestation walkthrough
PYTHONPATH=. python3 demo.py

# Prove an ALLOW authorization gates a real side effect and blocks replay
PYTHONPATH=. python3 demo_execution.py

# Prove changed tool endpoints and transaction destinations are blocked
PYTHONPATH=. python3 demo_tamper_enforcement.py

# Run the CMC RWA integration in offline fixture mode
PYTHONPATH=. python3 demo_cmc_rwa.py --fixture

# Run a real Solana Devnet execution: ALLOW -> broadcast -> confirmation
PYTHONPATH=. python3 demo_live_solana_devnet.py
# If the public faucet is rate-limited, use any funded Devnet keypair instead:
PYTHONPATH=. python3 demo_live_solana_devnet.py --sender-keypair path/to/devnet-id.json --skip-airdrop
# Optional: override the public Devnet RPC with VERIGATE_SOLANA_DEVNET_RPC_URL
```

### Portable authority proof

Verigate can export a **self-contained authority proof** that a third party can verify without access to the Verigate runtime, database, API, or live authority state.

A checked-in reference artifact lives in [`examples/authority-proof/`](examples/authority-proof/): it contains the proof package and the issuer's public key. The private key is never distributed.

Verify the artifact locally:

```bash
python cli.py verify examples/authority-proof/authority-proof.json \
  --public-key examples/authority-proof/issuer.pub \
  --format text
```

Or run the complete offline demonstration, which verifies the original artifact and then proves that a tampered copy is rejected:

```bash
python examples/authority-proof/verify_demo.py
```

The important property is **runtime independence**: after the proof is exported, verification consumes only the proof bytes and the trusted public key. The verifier does not query SQLite, the Verigate API, or a live authority ledger.

See [`examples/authority-proof/README.md`](examples/authority-proof/README.md) for the third-party verification walkthrough and trust model.

---

### CLI

```bash
# Generate an issuer keypair (auto-generated on first use if you skip this)
PYTHONPATH=. python3 cli.py keygen

# Check a payment intent against the default policy
PYTHONPATH=. python3 cli.py check \
  --agent trading-agent-001 --payee 0xMerchantABC \
  --asset USDC --network base --amount 10 --sign

# Verify a signed decision independently (only needs the public key)
PYTHONPATH=. python3 cli.py check ... --sign > attestation.json
PYTHONPATH=. python3 cli.py verify attestation.json

# See an agent's decision history
PYTHONPATH=. python3 cli.py history --agent trading-agent-001
```

### Judge demo UI

The browser UI lives at **http://localhost:8000/demo/**. It is a presentation layer over explicit demo endpoints; opening the page never implicitly enables live execution.

The canonical judge proof is the Genesis 2.0 command above. The UI is the visual execution/enforcement layer, not the source of truth.

For a safe local proof of execution-side enforcement:

```powershell
.\scripts\demo.ps1
# open http://localhost:8000/demo/
```

This enables only the deterministic tamper proof. It demonstrates: change the approved destination after authorization → **BLOCK** at the execution boundary → **0 broadcasts**.

For the explicit Solana Devnet demo, use:

```powershell
.\scripts\demo.ps1 -Live
```

`-Live` enables the real Devnet endpoint for that local process only. It may broadcast a real Devnet transaction and should not be enabled on a public deployment.

The endpoints are:

- `GET /demo/` — static judge UI, safe to serve by default.
- `GET /v1/demo/tamper` — deterministic enforcement proof; enabled by `VERIGATE_ENABLE_DEMO_TAMPER=true`.
- `GET /v1/demo/live` — real Solana Devnet execution; requires explicit `VERIGATE_ENABLE_DEMO_ENDPOINTS=true`.

The UI itself remains available even when execution endpoints are disabled, so a deployed instance does not silently become a transaction broadcaster just because `/demo/` is reachable.

Or with Docker:

```bash
docker compose up --build
```

```bash
curl -X POST http://localhost:8000/v1/check \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "trading-agent-001", "payee": "0xMerchantABC",
       "asset": "USDC", "network": "base", "amount": 10, "sign": true}'

curl http://localhost:8000/v1/public-key
```

---

## Writing a policy

Policies are plain YAML — see `policies/default.yaml` for a real, working
starting point (blocklist, allowlist, per-network/asset restrictions,
destination/egress scope, per-transaction cap, new-payee cap, daily cap,
confirmation threshold, rate limit — all commented).

For agent/tool integrations, `allowed_destinations` and
`blocked_destinations` bind the signed ActionIntent to its execution egress.
If a policy configures destination scope, a missing or out-of-scope destination
is **BLOCKED before executable authority is issued**. This closes the
zero-click pattern `untrusted input → tool invocation → attacker destination`
without relying on the model to recognize the attack.

No code changes needed to adjust any of it — edit the YAML, restart the
process.

---

## Project layout

```
core/
    models.py       PaymentIntent, ActionIntent, AgentIdentity, Capability, AuthorityEdge
    authority_protocol.py Canonical Genesis 2.0 Authority / lifecycle primitives
    intent_graph.py Intent Graph for consequential plans and dependencies
    authority_intent_graph.py Authority-aware plan assessment; eligibility is not authorization
    identity.py     Cryptographic identity registry + agent-signed intent verification
    authorization.py Protocol-agnostic receipt + execution-capability minting
    capabilities.py Capability registry + effective authority + revocation
    authority.py    Authority graph + cryptographic capability delegation
    authority_state.py Deterministic dynamic agent authority + evidence-driven limits
    evidence.py     Cryptographic provenance / Evidence Graph projection
    outcome.py      Independent execution outcome claims + trusted attestations
    adversarial.py  Mutation-based attack corpus + fail-closed authority verification
    policy_version.py Signed policy versions, governed publication, freeze/rollback control and lineage verification
    governance.py   Signed authority reset + multi-party quorum governance + epoch recovery
    policy.py       Policy loader (the one place PyYAML is used in core/)
    rules.py        Deterministic payment + protocol-agnostic action rule evaluators
    storage.py      SQLite-backed audit/rate/spend + authority graph persistence
    engine.py       GuardrailEngine — evaluates and binds identity/capability authority
attest/
    keys.py         Ed25519 keypair generation/loading
    sign.py          Sign a decision into a verifiable attestation
    verify.py         Independent verification (payload + public key only)
x402/
    parser.py       Parses a real x402 PAYMENT-REQUIRED header into a
                       normalized PaymentIntent
api/
    main.py         FastAPI app: check, capability-bound authorization,
                       identity-bound authorization, execution and verification endpoints
    schemas.py        Pydantic request/response models (API boundary only)
cli.py              check / verify / keygen / history commands
demo.py             End-to-end policy / attestation walkthrough
demo_execution.py    Real side-effect execution-gate demonstration
demo_evm_execution.py EVM adapter demo with a broadcaster boundary
enforcement/
    protocol.py       Chain-independent ExecutionAdapter boundary
    local.py          Fail-closed local execution adapter
    tool.py           MCP-style signed tool-call execution boundary
    http.py            Exact signed HTTP/API execution boundary
    router.py          Network + generic execution routing
    evm.py             Dependency-light EVM execution adapter
adapters/cmc/
    client.py         CoinMarketCap RWA v5 client
    models.py         Normalized RWA market evidence
    rwa.py            RWA purchase policy + authorization pack
hackathons/
    registry.yaml     Hackathon integrations and submission state
policies/default.yaml
tests/              Full automated suite: engine, attestation, x402, API, enforcement
```

`core/*` and `attest/*` are dependency-light on purpose (stdlib +
`cryptography` + `PyYAML` only, no FastAPI/pydantic) so the decision
engine can be embedded in another service or tested without installing
the API layer.

---

## Genesis architecture

Verigate is being expanded around a protocol-agnostic authority lifecycle:

**Identify → Propose → Verify → Decide → Authorize → Enforce → Observe → Prove → Learn**

The foundational path is:

`AgentIdentity → Capability → Delegated Capability → Dynamic Authority → ActionIntent → PolicyVersion → AuthorityDecision → ExecutionAuthorization → Execution → Evidence → Authority Update → Governance Epoch`

`AgentIdentity` is a cryptographic Ed25519 principal. The Identity Registry maps an identity fingerprint to an agent and supports revocation. An agent can sign the exact normalized `ActionIntent` before Verigate evaluates it.

A **Capability** is programmable authority: action scope, targets/resources, networks/assets, limits, conditions and expiry. The Capability Registry is the source of truth for effective active authority. A capability may be bound to a specific identity.

**Delegation is first-class.** A parent capability can create a child capability only when the parent identity signs the exact child definition. The child must be narrower or equal in every authority dimension: action/target/resource/network/asset scope, limits, conditions and lifetime. The relationship is persisted as a graph edge, allowing Verigate to explain authority provenance.

Effective authority is evaluated over the full ancestor chain. Revoking a parent capability or any required identity invalidates descendant authority for future decisions.

**Dynamic Agent Authority** is the next control layer below that static graph. A capability starts in `PROBATION`, is constrained to a deterministic fraction of its registered limits, and can progress to `STANDARD` and `ELEVATED` only through verified successful execution history. Adverse outcomes reduce authority; tamper and policy-violation evidence can suspend it. Dynamic authority never grants more than the static capability already grants.

**Multi-party governance** protects sensitive authority recovery from a single compromised governance key. A `GovernancePolicy` defines the quorum threshold, optional required roles and bounded approval lifetime. Each governor signs the exact governance-action digest, which also commits to the exact governance-policy digest. Signers are unique, approvals expire, nonces are persisted, and the quorum is checked before a new authority epoch can be opened. The HTTP control plane exposes the configured policy at `GET /v1/governance/policy` and the hardened recovery path at `POST /v1/authority/reset/multi`.

A **Decision Receipt** proves what Verigate decided. An **Execution Authorization** is distinct: only ALLOW can mint it, and the signed artifact contains the exact action fingerprint plus capability, identity and dynamic-authority fingerprints. The execution boundary consumes the artifact fail-closed. An **Execution Receipt** records what the executor reported, but it does not by itself change authority. An independent **Outcome Claim** binds the observed result to that signed receipt; a registered external or chain attestor can then sign an **Outcome Attestation**. Only those independent attestations automatically create `EXECUTION_CONFIRMED` / `EXECUTION_FAILED` authority events. Executor self-reports remain auditable evidence but cannot promote or demote the agent.

Revoking an identity or capability prevents future authorizations. It does not silently mutate an already-issued authorization; issued authority remains bound to the exact identity/capability versions that produced it.

Payment and x402 remain backward-compatible adapters while this general authority model expands to API, MCP, cloud, database, EVM, Solana and other execution environments.

## Roadmap

The core Genesis 2.0 protocol is now in proof/demo hardening rather than feature accumulation.

1. **Judge-grade presentation** — make the lifecycle, execution enforcement, portable proof and tamper rejection obvious in one short demo.
2. **Protocol conformance** — formalize the exact `verigate-authority-proof-v1` validity contract and publish adversarial conformance vectors.
3. **Hosted authority infrastructure** — multi-tenant key management, attestor lifecycle, governance operations and offline-verifiable evidence at service scale.

The rule for the next phase: do not add architecture unless it strengthens an independently demonstrable authority or proof boundary.

## License

MIT.


### Canonical authorization API

`POST /v1/authorize` remains the backward-compatible payment path.

`POST /v1/authorize/capability` resolves a registered active capability and binds it to one exact normalized action before minting `ExecutionAuthorization`.

`POST /v1/actions/authorize` is the canonical protocol-agnostic authority path. The caller supplies an exact `ActionIntent` plus an agent signature; Verigate verifies the registered identity, checks the identity-bound capability and its delegation ancestry, evaluates universal action policy, and only then mints execution authority. Actions include MCP tools, API requests, cloud/database changes, contract calls and payments.

`POST /v1/authorize/identity` remains the backward-compatible payment-shaped identity path. It normalizes its request into the same `ActionIntent` authority model.

`GET /v1/authority/capabilities/{capability_id}` explains the authority provenance of a capability, including its delegation path, graph edges and dynamic authority state.

`POST /v1/verify/adversarial` verifies a signed `ExecutionAuthorization` with the independent mutation corpus and reports whether every authority-tampering challenge is blocked.

`GET /v1/policies/{policy_sha256}` returns the signed policy version bound to a decision, allowing independent auditors to retrieve and verify the exact policy provenance. Governed publication uses `POST /v1/policies/governed/publish` with the signed policy artifact, a `POLICY_CHANGE` governance action and its quorum approvals; `GET /v1/policies/governed/{policy_sha256}` returns the complete governance envelope. Emergency control uses `POST /v1/policies/governed/freeze`; rollback uses `POST /v1/policies/governed/rollback`; `GET /v1/policies/governed/control/{policy_id}` exposes the current activation state. Freeze/rollback actions require quorum and are immutable replay-protected records. Set `VERIGATE_REQUIRE_GOVERNED_POLICY=true` on a deployment to make the authorization engine fail closed unless the active policy digest, version, source and parent are present in the governed registry.

`GET /v1/governance/public-key` exposes the compatibility governor public key. `POST /v1/authority/reset` remains the legacy single-governor recovery path. Production multi-party recovery uses `GET /v1/governance/policy` plus `POST /v1/authority/reset/multi`; the latter requires a configured quorum policy with threshold >= 2, exact-action approvals, unique signers, bounded approval lifetime and persisted replay protection.

A multi-party policy is supplied through `VERIGATE_GOVERNANCE_POLICY` and contains `policy_id`, `version`, `threshold`, `members`, optional `required_roles`, `max_approval_lifetime_seconds` and `allowed_actions`. `POLICY_CHANGE` must be included in `allowed_actions` for governed policy publication. Production control deployments should also allow `POLICY_FREEZE` and `POLICY_ROLLBACK`; keep `AUTHORITY_RESET` separate from policy operations when role separation is required. Each member is identified by the SHA-256 fingerprint of its raw Ed25519 public key and carries its base64-encoded raw public key plus governance role. Keep the policy file and private governance keys outside the repository; the repository should contain only the schema/configuration contract.

`ExecutionAuthorization` is short-lived, nonce-bound, and contains the authorized normalized action plus identity/capability fingerprints. The execution adapter consumes it; the decision receipt is evidence and is not itself permission to execute. The Execution Fabric now has generic `mcp.tool.call` and `api.request` boundaries in addition to chain-specific adapters; they execute only the exact signed action data and fail closed before consuming authority on unsupported targets or URL drift.

The **Evidence Graph** exposes this provenance as a deterministic subgraph. `/v1/evidence/authorization/{id}` and `/v1/evidence/intent/{id}` return the identity, agent signature, signed delegation path, governed policy lineage, freeze/rollback controls, authority reset, dynamic authority state, decision receipt, execution authorization, execution receipt, outcome claim, outcome attestation and resulting authority event when those artifacts exist. Each artifact is hash-addressed; missing delegation signatures, invalid governance approvals and invalid outcome attestations are surfaced as invalid evidence rather than silently treated as trusted links.

The outcome plane is exposed through `POST /v1/outcomes/attest` and `GET /v1/evidence/outcome/{authorization_id}`. Trusted attestors are durable registry entries rather than arbitrary public keys supplied in an attestation. Deployments can seed them with `VERIGATE_OUTCOME_ATTESTORS` as a JSON array of `attestor_id`, `public_key_b64` and `attestor_type` objects. `EXECUTOR` keys may self-report, but only `EXTERNAL_VERIFIER` or `CHAIN_VERIFIER` attestations can change dynamic authority automatically. Chain verifiers must supply `CHAIN_RECEIPT` evidence.

`POST /v1/authorize/x402` provides the compatibility contract for an x402 `PAYMENT-REQUIRED` header.

The existing `/v1/check` endpoints remain available for compatibility.
