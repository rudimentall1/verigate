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

For Anna `CHAIN_VERIFIER` proofs, add independently distributed wallet governance anchors:

```bash
verigate-verify proof.json --public-key issuer.pub \
  --trusted-governance-policy-sha256 <attestor-policy-sha256> \
  --trusted-wallet-governance-policy-sha256 <wallet-policy-sha256> \
  --trusted-wallet-enrollment-history-sha256 <wallet-history-sha256>
```

To add external rollback protection for Anna wallet governance, also provide the transparency log's public key and the latest checkpoint digest obtained independently from the log operator:

```bash
verigate-verify proof.json --public-key issuer.pub \
  --wallet-governance-log-public-key wallet-governance-log.pub.pem \
  --trusted-wallet-governance-checkpoint-sha256 <latest-checkpoint-sha256>
```

Both flags are required together. The verifier rejects a proof containing an older signed checkpoint when its digest differs from the independently trusted latest checkpoint. Without both out-of-band values, the log signature may still be checked, but the transparency anchor is reported as `NOT PINNED` and no rollback-resistance claim is made. The log writer is a reference component: production deployments must operate it separately from Verigate, with separate storage and key custody, and must deliver every governance action to it when accepted. See the [transparency log protocol](https://github.com/rudimentall1/verigate/blob/main/docs/wallet-governance-transparency-log-v1.md).

Repeat each digest flag for every explicitly trusted policy or history version. Obtain these values through a separate trusted channel. Without wallet pins, the verifier still checks the signed governance envelopes, quorum and registry snapshots, but reports the wallet trust anchors as `NOT PINNED`; it does not independently establish the governor roster or completeness of the supplied history.
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
