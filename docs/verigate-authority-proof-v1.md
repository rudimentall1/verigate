# Verigate Authority Proof Protocol v1

## Status

This document defines the interoperable verification contract for `verigate-authority-proof-v1`.

A conforming verifier MUST be able to verify a portable proof from the supplied JSON package and a trusted issuer public key. It MUST NOT require Verigate SQLite state, an API server, authority caches, or the issuer's runtime.

## Trust model

The issuer public key is the trust anchor. A verifier MUST obtain it from an independent trusted channel. The public key embedded in the signed manifest identifies the issuer but is not, by itself, a trust decision.

## Verification layers

A verifier MUST fail closed and perform these checks:

1. **Package integrity** — `package_sha256` equals the canonical SHA-256 of `package`.
2. **Manifest integrity** — `manifest_sha256` equals the canonical SHA-256 of `manifest`.
3. **Issuer signature** — the Ed25519 signature covers the canonical manifest payload.
4. **Trust anchor** — when a trusted public key is supplied, it equals the manifest issuer key.
5. **Graph integrity** — every node data hash, edge reference, node inventory, graph counts, and Merkle root match the signed manifest.
6. **Authority protocol** — authority-lifecycle proofs contain exactly the signed `verigate-authority-proof-v1` assertions and their assertion-set digest.
7. **Authorization** — the execution authorization signature, identity, capability, action, authority snapshot, policy bindings, timing, and execution graph bindings are valid.
8. **Historical authority** — the authorization's committed ledger head resolves to a valid historical ledger prefix; later ledger events MUST NOT invalidate the historical proof.
9. **Execution** — the execution receipt is cryptographically bound to the authorization.
10. **Outcome** — the outcome claim is bound to an independently generated `observed_effect` artifact, its exact observation digest/evidence reference/result digest, the execution receipt, and an independent attestation. The `observed_effect` artifact MUST be carried as a first-class proof node.
11. **Learning** — the authority event MUST be deterministic from the terminal outcome: `SUCCEEDED → EXECUTION_CONFIRMED` and `FAILED → EXECUTION_FAILED`; its identity, claim reference, event id, attestation metadata, and exact ledger entry MUST agree.
12. **Historical authority** — the pre-execution authority snapshot MUST be reproducible from the signed authority policy and the committed historical ledger prefix; counters, state, multiplier, reason, and policy window MUST recompute exactly.
13. **Post-learning authority** — the resulting authority state MUST be reproducible from the complete ledger at its evaluation time and the same signed authority policy, including counters, state, multiplier, reason, timestamps, and learning-event ledger head.

For `verigate-authority-proof-v1`, an authority-reset boundary that changes `history_start_at` must not be silently inferred from runtime state. Without a portable reset artifact and independently verifiable reset governance, the proof MUST fail closed rather than treating the reset boundary as trusted input.

## Historical semantics

Authorization expiry is evaluated at the recorded execution time for a historical proof. A verifier MUST NOT compare an already executed authorization to the verifier's current wall clock and invalidate it solely because the authorization has expired since execution.

This preserves the distinction between:

- **live enforcement:** is this authorization executable now?
- **historical proof:** was this authorization valid when the recorded execution happened?

## Required authority assertions

An authority-lifecycle proof contains nine assertions plus deterministic semantic conformance checks for historical authority and learning transition:

- A1 identity possesses capability
- A2 intent proposed by agent
- A3 authority permits intent
- A4 authorization derived from authority
- A5 execution consumed authorization
- A6 outcome observes execution and is supported by the canonical observed-effect artifact
- A7 learning event justified by outcome claim
- A8 post-learning authority state produced by learning event
- A9 post-learning state ledger-bound

These are semantic protocol assertions, not UI labels. Their exact signed representation and digest MUST match the manifest evidence.

## Result contract

A conforming verifier should expose at minimum:

```text
valid
protocol
root_digest
package_sha256
assertion_set_sha256 (authority lifecycle only)
checks
```

`valid=true` MUST mean all applicable protocol checks passed. Partial verification MUST NOT be reported as valid.

## Reference test vector

The repository's `examples/authority-proof/authority-proof.json` is the reference authority-lifecycle test vector. `examples/authority-proof/issuer.pub` is its issuer trust anchor.

The expected result for the unmodified vector is `VALID`. Mutating any covered package field MUST result in `INVALID`.
