# Verigate Authority Proof Protocol v1

## Status

This document defines the interoperable verification contract for `verigate-authority-proof-v1`.

A conforming verifier MUST be able to verify a portable proof from the supplied JSON package and a trusted issuer public key. It MUST NOT require Verigate SQLite state, an API server, authority caches, or the issuer's runtime.

## Trust model

The issuer public key is the trust anchor. A verifier MUST obtain it from an independent trusted channel. The public key embedded in the signed manifest identifies the issuer but is not, by itself, a trust decision.

The authority-lifecycle package also carries the governance policy and member public keys used for attestor registration. A verifier MUST cryptographically verify the policy fingerprint, every approval signature, member role, signer uniqueness, required roles, threshold, and historical validity window. This establishes that the action was approved by a quorum of the keys declared in that policy. It does **not** independently establish that those keys were the organisation's authorised governors. The standalone CLI accepts `--trusted-governance-policy-sha256 SHA256`; obtain each supplied digest through a separate trusted channel, not from the proof being verified. Repeat the flag for each policy version that is trusted, and the verifier requires every governance action in the attestor lineage to match one of those pinned digests. Without a supplied pin, the proof may still be cryptographically valid, but `governance_policy_trust_anchor.pinned` is `false` (the text report says `NOT PINNED`) and the embedded governor roster is not independently trusted. An issuer-signed policy node is evidence of which policy was presented, not an independent governance root of trust.

## Wallet enrollment governance evidence

For an Anna installation whose outcome attestation uses `CHAIN_VERIFIER`, the portable package MUST include the complete `wallet_enrollment_governance_history` node and every `wallet_enrollment` registry snapshot for that installation principal. The history node carries the complete set of signed `WALLET_ENROLL` / `WALLET_REVOKE` envelopes and its canonical SHA-256 digest. For deterministic pinning, the digest is SHA-256 over canonical JSON of the envelope array sorted by `action.action_id` in ascending lexical order; the state machine independently replays actions by their first-complete-quorum effective timestamp. Each wallet snapshot MUST be covered by the history node, and the matching enrollment MUST be linked to the execution receipt. The verifier MUST validate each governance policy, action fingerprint, approval signature, signer/nonce uniqueness, quorum and effective time, replay the enrollment state at the outcome's signed `attested_at`, reconcile every final registry snapshot, and verify the original execution receipt with the issuer key authorized by the historical active enrollment. A revoke after `attested_at` MUST NOT invalidate an earlier attestation; a revoke effective at or before `attested_at` MUST invalidate it. Re-enrollment MUST create an independently verified state transition rather than silently restoring an old enrollment.

The standalone verifier accepts two additional optional, repeatable trust anchors: `--trusted-wallet-governance-policy-sha256` pins every governor roster/policy used in the installation's wallet history, and `--trusted-wallet-enrollment-history-sha256` pins the canonical digest of the complete envelope list for that installation principal. Both digest sets MUST be obtained through a separate trusted channel. Without them, the verifier still checks the supplied signatures, quorum and snapshot consistency, but reports `pinned=false`; it MUST NOT claim the embedded roster is independently trusted or that the supplied history is independently complete. These anchors are separate from the attestor governance policy pin.

A proof MAY also carry a `wallet_governance_transparency_log` node linked from the wallet history node by `ANCHORED_BY`. A conforming verifier MUST validate the per-principal sequence numbers, previous-entry hashes, exact envelope set, checkpoint entry count/head/history digest, checkpoint digest and Ed25519 signature. To establish external log authenticity and freshness, the verifier MUST be given both `--wallet-governance-log-public-key` and `--trusted-wallet-governance-checkpoint-sha256` through an independent trusted channel. The supplied checkpoint digest MUST match the signed checkpoint in the proof. Supplying only one flag MUST fail closed. If neither is supplied, a valid embedded log signature is informational only; the verifier MUST report `wallet_governance_transparency_anchor.pinned=false` and MUST NOT claim rollback resistance. When both are supplied, a stale checkpoint MUST be rejected even if its signature remains valid. The log writer, database and signing key MUST be administered outside the Verigate service; see [Wallet Governance Transparency Log v1](wallet-governance-transparency-log-v1.md).

## Verification layers

A verifier MUST fail closed and perform these checks:

1. **Package integrity** — `package_sha256` equals the canonical SHA-256 of `package`.
2. **Manifest integrity** — `manifest_sha256` equals the canonical SHA-256 of `manifest`.
3. **Issuer signature** — the Ed25519 signature covers the canonical manifest payload.
4. **Trust anchor** — when a trusted public key is supplied, it equals the manifest issuer key.
5. **Graph integrity** — every node data hash, edge reference, node inventory, graph counts, and Merkle root match the signed manifest.
6. **Authority protocol** — authority-lifecycle proofs contain exactly the signed `verigate-authority-proof-v1` assertions and their assertion-set digest.
7. **Governance quorum and trust anchor** — for governed attestor lineage, the governance policy fingerprint and member-key fingerprints are valid; each Ed25519 approval signs the exact action; member roles, unique signers/nonces, required roles, and quorum threshold pass. Historical validity is evaluated at the latest issue time among the action and its approvals, when the complete quorum first existed, rather than against the verifier's current clock. Action and approval `issued_at`/`expires_at` values MUST be finite numbers; `NaN`, infinities, and values outside the supported numeric range MUST be rejected before time comparisons. Policy thresholds, required-role counts, and maximum approval lifetime MUST be positive integers. When one or more `--trusted-governance-policy-sha256` values are supplied, every policy digest in the lineage MUST match that allowlist or verification fails. Without a pin, the verifier explicitly reports `pinned=false`; cryptographic quorum validation alone does not establish the organisation's trusted governor roster.
8. **Authorization** — the execution authorization signature, identity, capability, action, authority snapshot, policy bindings, timing, and execution graph bindings are valid.
9. **Historical authority** — the authorization's committed ledger head resolves to a valid historical ledger prefix; later ledger events MUST NOT invalidate the historical proof.
10. **Execution** — the execution receipt is cryptographically bound to the authorization.
11. **Outcome** — the outcome claim is bound to an independently generated `observed_effect` artifact, its exact observation digest/evidence reference/result digest, the execution receipt, and an independent attestation. The `observed_effect` artifact MUST be carried as a first-class proof node. The Ed25519 attestation signature MUST verify against the governance-approved attestor key that was active at `attested_at`. The verifier MUST replay every quorum-approved `ATTESTOR_REGISTER`, `ATTESTOR_ACTIVATE`, `ATTESTOR_ROTATE`, `ATTESTOR_REVOKE`, and `ATTESTOR_EXPIRE` action, require the signed registry snapshot's final status/key/type/expiry and revocation marker to agree with that history, and select the historical key and authority state at attestation time. A later key rotation or revocation MUST NOT retroactively invalidate an attestation that was valid before the transition; a revocation or expiry effective at or before `attested_at` MUST invalidate it. Evidence-graph regeneration MUST replay the stored governance envelopes, verify their quorum approvals, and resolve each stored attestation against the historical key and authority state at its signed `attested_at`; it MUST NOT verify old signatures against only the current registry snapshot.
12. **Wallet enrollment** — for Anna `CHAIN_VERIFIER` proofs, the complete signed wallet governance history and all enrollment snapshots MUST be portable, digest-bound and reconciled. The verifier MUST replay `WALLET_ENROLL` and `WALLET_REVOKE` at `attested_at`, require exactly one matching historical active enrollment, check its binding to the receipt, and verify the receipt signature with that enrollment's issuer key. Optional out-of-band wallet policy and history digest allowlists MUST be checked when supplied; without pins the verifier MUST report both anchors as `pinned=false`.
12. **Wallet transparency log** — when a wallet transparency node is present, verify its complete append-only entry chain, exact envelope set, signed checkpoint, and graph binding to the wallet history. When external log trust is required, both the independently obtained log public key and latest checkpoint digest MUST be supplied and MUST match. Without those pins, the verifier MUST explicitly report the log anchor as unpinned.
13. **Learning** — the authority event MUST be deterministic from the terminal outcome: `SUCCEEDED → EXECUTION_CONFIRMED` and `FAILED → EXECUTION_FAILED`; its identity, claim reference, event id, attestation metadata, and exact ledger entry MUST agree.
13. **Historical authority** — the pre-execution authority snapshot MUST be reproducible from the signed authority policy and the committed historical ledger prefix; counters, state, multiplier, reason, and policy window MUST recompute exactly.
14. **Post-learning authority** — the resulting authority state MUST be reproducible from the complete ledger at its evaluation time and the same signed authority policy, including counters, state, multiplier, reason, timestamps, and learning-event ledger head.

For `verigate-authority-proof-v1`, an authority-reset boundary that changes `history_start_at` must not be silently inferred from runtime state. Without a portable reset artifact and independently verifiable reset governance, the proof MUST fail closed rather than treating the reset boundary as trusted input.

## Governance policy pinning

Use an independently distributed policy digest as an additional trust anchor:

```text
python tools/verigate_proof_verifier.py proof.json --public-key issuer.pub --trusted-governance-policy-sha256 <trusted-policy-sha256>
```

For multiple explicitly trusted policy versions, repeat `--trusted-governance-policy-sha256` once per digest. The allowlist is checked against every governance action in the attestor lineage, not just the latest action. A digest is the canonical SHA-256 policy fingerprint carried by the signed governance action. An empty or malformed digest is rejected; a well-formed but untrusted digest invalidates the proof.

For Anna `CHAIN_VERIFIER` proofs, independently pin the wallet governance policy and complete installation history as well:

```text
python tools/verigate_proof_verifier.py proof.json --public-key issuer.pub \
  --trusted-governance-policy-sha256 <attestor-policy-sha256> \
  --trusted-wallet-governance-policy-sha256 <wallet-policy-sha256> \
  --trusted-wallet-enrollment-history-sha256 <wallet-history-sha256>
```

Repeat either wallet flag for every independently trusted policy or history version. The history digest covers the complete canonical list of stored wallet governance envelopes for the installation principal. It must be distributed independently of the proof. Omitting either flag does not bypass signature/quorum checks, but leaves that trust anchor explicitly unpinned.

## Attestor governance history

Governed attestor evidence is interpreted as an ordered state machine. A registration creates an active key; activation changes the status to active; rotation replaces the key/type/expiry and reactivates the attestor; revocation changes an active attestor to revoked; expiry changes a registered attestor to expired. Every action MUST have a valid policy quorum, and the complete signed action sequence MUST reproduce the final attestor registry snapshot. The outcome signature is checked against the key and status produced by the sequence at `attested_at`, not against whichever key happens to be latest in the proof. Governance actions become effective for portable verification at the first timestamp when the action and its complete approval quorum existed.

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
