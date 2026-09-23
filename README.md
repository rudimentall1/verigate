# Verigate

**Agent Authority Control Plane for autonomous agents.**

An AI agent can propose an action. Verigate establishes the authority under which it may execute, then enforces and proves what actually happened. Identity, capabilities, policy, execution and evidence are protocol-agnostic; payments and blockchains are adapters, not the product boundary.

Your agent wants to pay for something — a data feed, an API call, an
invoice, an x402 `PAYMENT-REQUIRED` offer. Verigate checks that payment
against rules you wrote, before it happens, decides ALLOW / WARN / BLOCK,
and cryptographically signs the decision — so a partner, auditor, or
counter-party can verify it actually happened and hasn't been altered,
**without trusting your server, your logs, or your dashboard.**

```
x402 offer / raw payment intent
            |
            v
   ┌─────────────────────┐
   │   Policy Engine       │   deterministic rules: caps, allowlists,
   │   (guardrail/*)         │   rate limits, new-payee/daily limits
   └─────────────────────┘
            |
            v
     ALLOW / WARN / BLOCK
            |
            v
   ┌─────────────────────┐
   │  Ed25519 Attestation   │   signed with the issuer's private key
   └─────────────────────┘
            |
            v
   anyone with the PUBLIC key can verify the decision independently
```

---

## Why this, not another agent-risk dashboard

The core problem is broader than payments: autonomous agents increasingly
need authority to call APIs, use MCP tools, change cloud resources, write
data, move money, execute contracts and perform other consequential actions.

Verigate therefore treats payment as one execution adapter inside a general
authority lifecycle. The critical boundary is not a dashboard or a risk
number; it is the verifiable chain from **identity → capability → exact
intent → decision → authorization → execution → evidence**.

Most answers to that gap are "trust our dashboard" — a vendor's server
decides, logs the decision, and shows you a UI. Verigate's decisions are
**independently checkable**: the signature is a mathematical proof over
the decision payload, verifiable by anyone holding the public key, with
no API call back to Verigate required. If a decision is presented to you
after the fact — by a counter-party, in a dispute, for an audit — you can
verify it was genuine and untampered without ever trusting the party who
handed it to you.

It is also **not blockchain- or protocol-specific**. The policy engine
operates on a normalized `PaymentIntent` — x402 is the first protocol
adapter, but the same engine, same policy file, and same signed-decision
model apply to any payment rail you write a normalizer for.

---

## Who this is for

- Teams shipping agents that spend real money (via x402, AP2, or a custom
  rail) who need org-level spend controls the protocol itself doesn't
  provide.
- Anyone who has to **prove** to a finance team, an auditor, or a
  counter-party what an agent was and wasn't allowed to do — not just
  assert it.

---

## Honesty about the current state

This is a real, runnable, tested policy engine and attestation
system — not yet a hosted product. Specifically:

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
| Authorization service | **Real.** Generic `ActionIntent` decisions can mint the same portable receipt and one-time authority used by payment and other execution flows. |
| Execution enforcement boundary | **Real.** One-time signed capabilities are consumed fail-closed; the local and dependency-light EVM adapters share the same gate. |
| Multi-tenant / hosted key management | **Not built.** Today, one issuer keypair per deployment, loaded from a local file. |

---

## Quickstart

```bash
pip install -r requirements.txt

# Run the tests (fast, no network, no API layer needed)
PYTHONPATH=. python3 -m unittest discover -s tests -v

# See the full story end-to-end: a real x402 header parsed, evaluated,
# signed, and independently verified — including a tamper-detection check.
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

The browser UI lives at **http://localhost:8000/demo/**, but the demo execution endpoints are disabled by default. This is intentional: opening a web page must never implicitly expose a live blockchain execution endpoint.

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
per-transaction cap, new-payee cap, daily cap, confirmation threshold,
rate limit — all commented).

No code changes needed to adjust any of it — edit the YAML, restart the
process.

---

## Project layout

```
core/
    models.py       PaymentIntent, ActionIntent, AgentIdentity, Capability, AuthorityEdge
    identity.py     Cryptographic identity registry + agent-signed intent verification
    authorization.py Protocol-agnostic receipt + execution-capability minting
    capabilities.py Capability registry + effective authority + revocation
    authority.py    Authority graph + cryptographic capability delegation
    policy.py       Policy loader (the one place PyYAML is used in core/)
    rules.py        Deterministic rule evaluators
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
    evm.py            Dependency-light EVM execution adapter
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

`AgentIdentity → Capability → Delegated Capability → ActionIntent → Policy + Context + Intelligence → AuthorityDecision → ExecutionAuthorization → Execution → Evidence`

`AgentIdentity` is a cryptographic Ed25519 principal. The Identity Registry maps an identity fingerprint to an agent and supports revocation. An agent can sign the exact normalized `ActionIntent` before Verigate evaluates it.

A **Capability** is programmable authority: action scope, targets/resources, networks/assets, limits, conditions and expiry. The Capability Registry is the source of truth for effective active authority. A capability may be bound to a specific identity.

**Delegation is first-class.** A parent capability can create a child capability only when the parent identity signs the exact child definition. The child must be narrower or equal in every authority dimension: action/target/resource/network/asset scope, limits, conditions and lifetime. The relationship is persisted as a graph edge, allowing Verigate to explain authority provenance.

Effective authority is evaluated over the full ancestor chain. Revoking a parent capability or any required identity invalidates descendant authority for future decisions.

A **Decision Receipt** proves what Verigate decided. An **Execution Authorization** is distinct: only ALLOW can mint it, and the signed artifact contains the exact action fingerprint plus capability and identity fingerprints. The execution boundary consumes the artifact fail-closed.

Revoking an identity or capability prevents future authorizations. It does not silently mutate an already-issued authorization; issued authority remains bound to the exact identity/capability versions that produced it.

Payment and x402 remain backward-compatible adapters while this general authority model expands to API, MCP, cloud, database, EVM, Solana and other execution environments.

## Roadmap

1. **Dynamic Agent Authority** — use verified history and outcomes to expand, reduce or probationarily constrain capabilities without bypassing deterministic policy.
2. **Adversarial Verification Plane** — independently challenge proposed authority and build a reusable regression/attack corpus.
3. **Signed policy versions** — bind each authority decision to the exact policy version and provenance that produced it.
4. **Hosted, multi-tenant key management** — move beyond one local issuer keypair while keeping offline verification.
5. **Reference execution integrations** — MCP, API, cloud, database and additional payment/chain adapters all consuming the same authority contracts.

## License

MIT.


### Canonical authorization API

`POST /v1/authorize` remains the backward-compatible payment path.

`POST /v1/authorize/capability` resolves a registered active capability and binds it to one exact normalized action before minting `ExecutionAuthorization`.

`POST /v1/authorize/identity` is the canonical cryptographic authority path. The caller supplies an exact intent plus an agent signature; Verigate verifies the registered identity, checks the identity-bound capability and its delegation ancestry, evaluates policy, and only then mints execution authority.

`GET /v1/authority/capabilities/{capability_id}` explains the authority provenance of a capability, including its delegation path and graph edges.

`ExecutionAuthorization` is short-lived, nonce-bound, and contains the authorized normalized action plus identity/capability fingerprints. The execution adapter consumes it; the decision receipt is evidence and is not itself permission to execute.

`POST /v1/authorize/x402` provides the compatibility contract for an x402 `PAYMENT-REQUIRED` header.

The existing `/v1/check` endpoints remain available for compatibility.
