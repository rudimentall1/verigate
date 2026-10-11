# Verigate threat model (v0.1)

Scope: the authority lifecycle - action intent, authority decision, signed execution
authorization, execution-side enforcement, evidence, and independent verification.

## What we protect

1. The issuer private key, which signs decisions and authorizations.
2. Integrity of signed authorizations and portable evidence.
3. One-time use of execution authority (no replay, no double spend).
4. Policy, capability and identity registries, i.e. what an agent is allowed to do.
5. Tenant separation, when multi-tenant mode is enabled.

## Adversaries

- **A. Compromised or prompt-injected agent.** Proposes actions outside its authority,
  inflates amounts, forges an identity, or reuses authority.
- **B. Untrusted client or network attacker.** Replays or tampers with authorizations and
  proofs, or calls the API without credentials.
- **C. Malicious tenant.** Tries to read or influence another tenant's authority.
- **D. Post-hoc tamperer** (including someone with database access after execution). Rewrites
  evidence to change what appears to have happened.
- **E. Component substitution.** Swaps the registered executor or handler.
- **F. Supply chain.** A vulnerable or malicious dependency.

## Controls in place

| Threat | Control |
|---|---|
| A: out-of-authority action | Deterministic policy engine (caps, allowlists, rate and daily limits, no statistical scores); capability ceilings; dynamic authority can never exceed the static ceiling; static revocation is final |
| A: amount manipulation | Exact Decimal comparison for caps (`core/money.py`); NaN, infinity and negative amounts rejected |
| A: forged identity | Ed25519 agent identities registered by fingerprint; agent-signed intents; `VERIGATE_REQUIRE_SIGNED_INTENT` closes the unsigned path |
| A/B: replay, double spend | One-time execution nonces consumed fail-closed by the router before execution; covered by a multi-process concurrency test |
| B: unauthenticated API | API-key authentication, default-deny once configured; `VERIGATE_REQUIRE_AUTH` fails closed; constant-time key comparison |
| C: cross-tenant access | Opt-in per-tenant issuer keys and tenant-scoped API credentials |
| D: evidence tampering | Ed25519 signatures; standalone verifier needs only the proof bytes and a trusted public key; adversarial mutation corpus; CLI `verify` requires an explicit trusted issuer key |
| E: handler substitution | Handler fingerprint binding; router binds adapter, target and execution artifact |
| Policy abuse | Signed policy versions; governed publication with quorum and role separation; freeze and rollback |
| F: supply chain | Full automated test suite in CI; dependency ranges constrained in `requirements.txt` |

## Known gaps and non-goals

- **Transitive executor confinement.** A trusted handler can still create child effects that
  Verigate does not see. The default scope is `direct`; see README.
- **Key custody.** Issuer keys live on local disk (optionally encrypted at rest). There is no
  KMS/HSM integration or key-rotation tooling yet.
- **Storage.** SQLite, single process. Multiple replicas need shared storage or a real database.
- **Availability.** The API has not been load-tested and has no volumetric DoS protection;
  deploy behind a reverse proxy.
- **Open by default.** Without `VERIGATE_API_KEYS` or `VERIGATE_REQUIRE_AUTH` the API is open
  and demo routes exist behind flags. Use the baseline in `docs/security-configuration.md`.
- **Policy quality.** Verigate enforces the configured policy; it does not judge whether the
  policy is wise.
- **No independent audit yet.**

## Assumptions

The issuer private key is not compromised, the host is trusted, and verifiers obtain the
issuer public key through a trusted channel.
