# verigate-verify

Offline verifier for [Verigate](https://github.com/rudimentall1/verigate) authority proofs.

Verigate decides, per action, whether an AI agent had the authority to act, issues a one-time signed
authorization, and exports a portable proof. This package is the standalone verifier for that proof:
**you need only the proof file and the issuer's Ed25519 public key.** No Verigate server, database or API.

## Install

```bash
pip install verigate-verify
```

## Use

```bash
verigate-verify proof.json --public-key issuer.pub
verigate-verify proof.json --public-key issuer.pub --format json
# or
python -m verigate_verify proof.json --public-key issuer.pub
```

The result is `VALID` or `INVALID` with a reason (for example `proof package digest mismatch` if the
evidence was altered). Exit code is 0 for a valid proof and non-zero otherwise.

A sample proof and issuer key are in the repository under `examples/authority-proof/`.

## What it does and does not tell you

It checks the package digest, the evidence manifest, the issuer signature against the public key you trust,
the evidence graph and the authority protocol assertions. It does not decide whether the issuer's key is the
right one to trust (you must obtain the public key through a channel you trust), and it does not prove that no
other actions were taken. See the [threat model](https://github.com/rudimentall1/verigate/blob/main/docs/threat-model.md).

## Source

This is the same code as `tools/verigate_proof_verifier.py` in the main repository. MIT licensed.
