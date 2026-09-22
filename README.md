# Verigate

**The authorization and proof layer between an autonomous AI agent and the real world.**

AI can propose an action. VeriGate deterministically authorizes it, and cryptography makes the authorization independently verifiable. Payments are the first vertical; the core model is protocol-agnostic.

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

Agentic payments (x402, AP2, and similar protocols) are explicitly
designed with **no human in the loop by default** — the point of the
protocol is that nothing sits between "agent wants to pay" and "money
moves." That is also the gap: every deployment ships with zero
organization-level governance unless someone adds it.

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

### API

```bash
uvicorn api.main:app --reload
```

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
    models.py      PaymentIntent, RuleMatch, GuardrailDecision (stdlib only)
    policy.py        Policy loader (the one place PyYAML is used in core/)
    rules.py          Deterministic rule evaluators
    storage.py         SQLite-backed audit log, rate limiter, spend tracking
    engine.py           GuardrailEngine — orchestrates rules -> decision
attest/
    keys.py         Ed25519 keypair generation/loading
    sign.py          Sign a decision into a verifiable attestation
    verify.py         Independent verification (payload + public key only)
x402/
    parser.py       Parses a real x402 PAYMENT-REQUIRED header into a
                       normalized PaymentIntent
api/
    main.py         FastAPI app: /v1/check, /v1/check/x402, /v1/verify,
                       /v1/public-key, /v1/agents/{id}/history
    schemas.py        Pydantic request/response models (API boundary only)
cli.py              check / verify / keygen / history commands
demo.py             End-to-end policy / attestation walkthrough
demo_execution.py    Real side-effect execution-gate demonstration
enforcement/
    protocol.py       Chain-independent ExecutionAdapter boundary
    local.py          Fail-closed local execution adapter
policies/default.yaml
tests/              Full automated suite: engine, attestation, x402, API, enforcement
```

`core/*` and `attest/*` are dependency-light on purpose (stdlib +
`cryptography` + `PyYAML` only, no FastAPI/pydantic) so the decision
engine can be embedded in another service or tested without installing
the API layer.

---

## Genesis architecture

VeriGate is being expanded around a protocol-agnostic authorization lifecycle:

**Discover → Authorize → Enforce → Prove → Learn**

The foundational `ActionIntent` model represents consequential agent actions such as API calls, tool invocations, cloud operations, wallet transactions, and payments. Payment rails remain adapters rather than the core abstraction.

A **Decision Receipt** binds the normalized action, resulting decision, and SHA-256 fingerprint of the effective policy into a signed Ed25519 proof. It proves what Verigate decided. An **Execution Authorization** is separate: only an ALLOW decision can mint this short-lived, nonce-bound capability for an executor. WARN and BLOCK never receive execution authority.

The existing `PaymentIntent` and x402 path remain backward-compatible while this generic authorization layer is introduced incrementally.

## Roadmap

1. AP2 and additional payment-rail adapters (same `PaymentIntent` seam).
2. Hosted, multi-tenant key management (today: one local keypair).
3. Signed policy versions, so an attestation can also prove *which*
   policy version produced a decision, not just the decision itself.
4. Webhook/event stream for real-time WARN confirmation (today: poll
   `/v1/agents/{id}/history` or use the CLI).
5. Reference integrations for common agent frameworks (LangChain, CrewAI,
   a raw MCP tool wrapper).

## License

MIT.


### Canonical authorization API

`POST /v1/authorize` returns two distinct artifacts: a signed `DecisionReceipt` proving the policy decision, and an `ExecutionAuthorization` only when the decision is ALLOW.

`ExecutionAuthorization` is short-lived and nonce-bound. It is the capability an execution adapter can accept; the decision receipt is evidence and is not itself permission to execute.

`POST /v1/authorize/x402` provides the same contract for an x402 `PAYMENT-REQUIRED` header.

The existing `/v1/check` endpoints remain available for compatibility.
