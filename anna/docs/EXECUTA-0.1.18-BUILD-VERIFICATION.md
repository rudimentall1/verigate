# Executa 0.1.18 — four-platform build verification

**Date:** 2026-11-11  
**Source commit:** `1afe3a4f35f945cc458cc705d59b400441e480cd`  
**Workflow:** [Build Anna Executa binaries — run 42989643581](https://github.com/rudimentall1/verigate/actions/runs/42989643581)  
**Event:** `workflow_dispatch` · **version:** `0.1.18` · **publish_release:** `false`

## CI result

All four matrix jobs completed successfully. Each performed two builds for reproducibility, packaged the executable, smoke-tested the extracted package, and uploaded the artifact.

| Target | Runner | Artifact ID | Artifact ZIP SHA-256 | Inner package SHA-256 |
|---|---|---:|---|---|
| Linux x86_64 | ubuntu-22.04 | 13841790228 | `b7951e94763b04ba069471db2c75f760f66339bf95ddf96b6da8970c2520c27c` | `85b4d2db9edd68189ae9e7cbd0cee1ac9852ef2f65048ccf49eeead13fdc88dc` |
| Windows x86_64 | windows-latest | 13840727568 | `4afd37108666c5b9c25980b9684fcb3eb95ba57920c867ba376fa082e4451f52` | `428d343bf77c65baacd2ba2056da4b7c4f1b99c451498f6f0d5b9e083d444c90` |
| macOS ARM64 | macos-26 | 13840293987 | `c2035ab753aa988282920b70b288ef87167a4b8f0ad87c71a7f7d732bffde3b2` | `2ffa9fa1c6f36797de9ea379caf87bc2796181506f57bce864933b47189e3a74` |
| macOS Intel x86_64 | macos-26-intel | 13840619039 | `ff5bfe2bd4b6164183bcd581f005fd5953832417478773563d7a5750ff54cc66` | `3dc93fef9d5f7138a3aab0938a9029fc05a4610c0eb413dbfbb2a66073193951` |

## Independent artifact inspection

All four GitHub workflow artifacts were downloaded and inspected. For every target:

- the outer artifact ZIP SHA-256 matched GitHub's artifact digest;
- the embedded package SHA-256 matched its `.sha256` sidecar;
- the package manifest declares Executa version `0.1.18`;
- the expected entrypoint is present: `verigate-authority` on Linux/macOS and `verigate-authority.exe` on Windows.

The Linux/macOS packages contain a `.tar.gz` release archive plus checksum sidecar. The Windows package contains a `.zip` release archive plus checksum sidecar.

## Release and Anna Console boundary

- The workflow's `release` job was **skipped**, as requested by `publish_release=false`. No GitHub Release or public tag is claimed by this run.
- The artifacts are GitHub Actions artifacts and expire **2027-02-09**.
- This workflow does **not** upload the package to Anna CDN or update Anna Console.
- The 11 November Console upload is now confirmed: immutable Draft App **0.1.31** (version ID **2110**) with bundled Executa **0.1.18** (version ID **1064**). All four platform archives were uploaded to Anna CDN and the App cut completed successfully.
- The App 0.1.31 Console cut now bundles Executa 0.1.18, satisfying the source manifest requirement `>=0.1.18`.

## Next release gate

The immutable Console cut is complete. Remaining acceptance work is to verify a fresh Cloud Agent install/invocation using Executa **0.1.18**, inspect live Runtime behavior, and validate platform-side APS concurrency/ETag and failure/late-response semantics. The App remains Draft; no review submission or Marketplace release was performed.

## What this evidence does not prove

This report records CI builds, runner smoke tests, downloaded artifact structure and checksum verification. It does not claim execution on four physical user devices, live Anna APS ETag/concurrency semantics, a fresh Cloud Agent installation, or a successful wallet transaction using Executa 0.1.18.
