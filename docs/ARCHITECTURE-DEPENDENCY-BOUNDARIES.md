# Verigate package dependency boundaries

**Status:** dependency-cycle remediation implemented in Draft PR #88; final CI and fresh analyzer verification pending.  
**Date:** 2026-11-28.

## Intended dependency direction

Verigate uses four logical layers:

- `core` owns protocol-agnostic domain models, identity/capability/policy evaluation, authority state, rules, storage contracts/implementations, and lower-level proof primitives. It must not import `attest`, `enforcement`, `application`, or API modules.
- `attest` owns signed DecisionReceipt and ExecutionAuthorization issuance/verification, historical authority replay, adversarial authorization checks, and signed evidence-graph construction. It may depend on core domain and persistence primitives.
- `enforcement` owns execution gates, routers, chain/tool adapters, and effect verification. It may depend on `core` and `attest`.
- `application` owns composition roots and workflows that combine core policy/evaluation with attestation and enforcement, including the configured GuardrailEngine, Genesis lifecycle, and governed wallet enrollment.

The intended graph is:

```text
             application
             /    |    \
            v     v     v
          core <- attest
            ^       ^
            |       |
            +-- enforcement
```

More precisely: `attest -> core`; `enforcement -> attest/core`; `application -> core/attest/enforcement`. There must be no reverse dependency from `core` to any of these higher layers.

## Cycles found by the architecture scan

The initial scan [run #46112311890](https://github.com/rudimentall1/verigate/actions/runs/46112311890) reported a three-package cycle across `attest`, `core`, and `enforcement`. The first import evidence identified:

- `core/adversarial.py` importing `attest.receipt.verify_execution_authorization`.
- `core/genesis_lifecycle.py` importing `enforcement.router.ExecutionRouter`.

After those two modules were moved, a second report [run #46116545770](https://github.com/rudimentall1/verigate/actions/runs/46116545770) reported a two-package cycle between `core` and `attest`. The exact remaining edges were:

- `core/authorization.py` imported attestation receipt/authorization functions.
- `attest/authority_replay.py` imported core authority-state models and policies.

Further inspection showed that `core/evidence.py` also imported `attest.receipt`, and that authorization issuance and evidence graph assembly were in the wrong package even though the initial cycle diagnostic highlighted only one edge pair.

## Remediation in PR #88

The source now places responsibilities with their owning layer:

| Original module | New module | Reason |
|---|---|---|
| `core/adversarial.py` | `attest/adversarial.py` | Challenge harness verifies signed execution-authority artifacts. |
| `core/authority_replay.py` | `attest/authority_replay.py` | Historical replay verifies a signed authorization against the authority ledger. |
| `core/authorization.py` | `attest/authorization.py` | Concrete service signs DecisionReceipt and ExecutionAuthorization artifacts. |
| `core/evidence.py` | `attest/evidence.py` | Evidence graph verifies signed authorization, receipts, identity and governance evidence. |
| `core/evidence_service.py` | `attest/evidence_service.py` | Persistent graph snapshots are an attestation/evidence responsibility. |
| `core/offline_verifier.py` | `attest/offline_verifier.py` | Runtime-independent verification of signed portable evidence is an attestation responsibility. |
| `core/proof_package.py` | `attest/proof_package.py` | Versioned signed proof transport/verification wraps attestations; it is not a core domain primitive. |
| `core/genesis_lifecycle.py` | `application/genesis_lifecycle.py` | Genesis composes core services, enforcement router, outcome service and proof package. |
| `core/wallet_enrollment.py` | `application/wallet_enrollment.py` | Governed installation-wallet enrollment is application workflow orchestration. |

The old modules are removed; no compatibility re-exports were added because those would reintroduce reverse package edges.

`core.authorization` now contains only the `AuthorizationArtifactIssuer` protocol (the dependency-inversion port). `core.engine.GuardrailEngine` accepts that port but does not know the concrete attestation implementation. `application.engine.GuardrailEngine` composes the core engine with `attest.authorization.AuthorizationService` for application flows that issue signed artifacts. The API and authorization tests use the application composition.

The API route remains `POST /v1/verify/adversarial`; the public route and authorization payload format are not intentionally changed. `attest.proof_package` preserves the previous proof-package serialization/verification functions and byte format; only the internal module path changes.

## Security invariants preserved

No intentional changes were made to:
- Ed25519 canonicalization or signatures;
- DecisionReceipt or ExecutionAuthorization fields;
- capability/identity bindings, policy binding, or authorization expiry;
- nonce consumption and replay protection;
- enforcement adapters or adapter contracts;
- broadcast ordering or side-effect behavior.

The changes are package ownership, dependency injection, and import-path updates. The core-only engine still supports policy evaluation; an application requiring signed authorization must provide the issuer through the application composition root.

## Verification

- The first test-first import-only stage intentionally failed because the destination modules did not yet exist: [CI #46115786079](https://github.com/rudimentall1/verigate/actions/runs/46115786079).
- The first source-move stage passed 698 Python tests and 69/69 Anna UI tests: [CI #46115841371](https://github.com/rudimentall1/verigate/actions/runs/46115841371). That result predates the additional service moves described above and does not verify the current head.
- The second architecture scan [#46116545770](https://github.com/rudimentall1/verigate/actions/runs/46116545770) still reported one module cycle between `core` and `attest`. The subsequent scan at run #46120175666 again isolated `core/offline_verifier.py` as the remaining reverse edge. Both offline verification and proof-package handling have now moved into `attest`.
- **Verification of the current source head is pending.** Do not report the cycle count as zero until a fresh report on the current head confirms it. Do not claim tests pass until the latest CI run for the final commit succeeds.
- No live chain execution or live payment was performed.
