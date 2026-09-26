# Portable Authority Proof

This directory contains a real, self-contained Verigate authority proof that can be verified **without a Verigate server, SQLite database, API, or live runtime**.

## Files

- `authority-proof.json` — the signed, self-contained proof package.
- `issuer.pub` — the Ed25519 public key used to authenticate the proof issuer.

The private signing key is **not** included.

## Verify it independently

From the repository root:

```bash
python cli.py verify examples/authority-proof/authority-proof.json --public-key examples/authority-proof/issuer.pub --format text
```

Expected result:

```text
VERIGATE AUTHORITY PROOF
Protocol: verigate-authority-proof-v1

CRYPTOGRAPHIC MANIFEST     PASS
AUTHORITY PROTOCOL         PASS
AUTHORIZATION              PASS
EXECUTION                  PASS
HISTORICAL AUTHORITY       PASS
LEARNING / POST-AUTHORITY  PASS

RESULT: VALID
```

The verifier reads the proof package and public key locally. It does not connect to the Verigate runtime or query its database. For a historical execution, authorization expiry is evaluated at the recorded execution time, not at the verifier's current wall clock; otherwise a valid old proof would become unverifiable merely because time passed.

## What the proof establishes

The `authority_lifecycle` proof binds one consequential action across the full Genesis 2.0 lifecycle:

```text
IDENTITY
   ↓
CAPABILITY
   ↓
INTENT
   ↓
AUTHORITY
   ↓
AUTHORIZATION
   ↓
EXECUTION
   ↓
OBSERVATION
   ↓
LEARNING
   ↓
POST-LEARNING AUTHORITY
   ↓
CRYPTOGRAPHIC PROOF
```

The package contains the signed evidence graph, authority history, execution receipt, independently attested outcome, learning event, post-learning authority state, and nine machine-verifiable authority assertions.

## Tamper test

Copy the proof and change any signed field. For example, change the package `agent_id`:

```bash
python -c "import json; p='examples/authority-proof/authority-proof.json'; d=json.load(open(p)); d['package']['agent_id']='tampered-agent'; json.dump(d, open('examples/authority-proof/tampered.json'))"
python cli.py verify examples/authority-proof/tampered.json --public-key examples/authority-proof/issuer.pub --format text
```

The verifier must exit non-zero and report:

```text
RESULT: INVALID
```

## Trust model

The public key is the trust anchor. A verifier should obtain that key from a trusted channel and compare it with the issuer key embedded in the signed manifest. Possessing the proof package alone is not enough to forge a new valid proof.

The package is a transport artifact. Verification is performed against the signed evidence manifest and the `verigate-authority-proof-v1` protocol; no Verigate runtime state is consulted.

## Regenerate the reference artifact

The checked-in artifact is intentionally fixed so the repository has a stable public proof to inspect. To create a fresh reference package with a new ephemeral issuer key, run:

```bash
python examples/authority-proof/generate_artifact.py
```

The generator uses a stable logical policy source reference (`examples/authority-proof/policy.yaml`) rather than embedding a developer machine path. The generated private issuer key is temporary and is never written into the repository.

## Genesis 2.0 demo\n\nRun the complete portable-proof demonstration:\n\n```bash\npython examples/authority-proof/run_demo.py\n```\n\nThe demo invokes the standalone verifier in a separate process using only `authority-proof.json` and `issuer.pub`. It does not start or query a Verigate runtime. It then mutates the proof and requires the independent verifier to reject it. A successful run ends with `GENESIS 2.0 DEMO: PASS`.\n\n## Standalone protocol verifier

A verifier implementation that imports no `core` or `attest` modules is included at `tools/verigate_proof_verifier.py`.

```bash
python tools/verigate_proof_verifier.py examples/authority-proof/authority-proof.json --public-key examples/authority-proof/issuer.pub
```

It validates the package, signed manifest, external trust anchor, graph/Merkle integrity, authority assertions, historical authority binding, authorization, execution, outcome, learning, and post-learning ledger binding without starting the Verigate runtime.
