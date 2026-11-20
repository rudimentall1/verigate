# Anna Release Checkpoint — Dual-Account Rule

**Last updated:** 2026-11-20  
**Applies to:** every Verigate Anna release  
**Branch:** `ANNA`

## Mandatory release rule

Every Verigate Anna release must be uploaded to **both** Anna Developer accounts: one is the primary account and one is the test account. Neither destination is optional. Both must receive the same release candidate (App version, bundled Executa version, source commit, and binary artifact set).

Never decide the destination from whichever account happens to be logged in. Route by the exact App ID and the matching account-specific Executa tool ID below.

| Anna Developer App | Account's bundled Executa | Executa tool ID | Developer Console |
|---|---:|---|---|
| **851** | **1314** | `tool-verigate-authority-verigate-authority-28x5jku8` | https://anna.partners/developer?app=851&tab=versions |
| **382** | **1164** | `tool-rinat-verigate-authority-2um8gwhw` | https://anna.partners/developer?app=382&tab=versions |

These are separate account identities. Do not swap the IDs, reuse one account's `.anna` identity files in the other account's project, or manually edit cached identity metadata to force an ID match.

## Required release procedure

1. Select one validated release candidate and freeze its source commit, App version, Executa version, and four platform binaries/checksums.
2. For App **851**, switch to its own Anna credentials. Verify `whoami`, `apps list`, and `executa list`; confirm App ID **851** and Executa ID/tool ID **1314 / tool-verigate-authority-verigate-authority-28x5jku8** before uploading. Stop if any identity does not match.
3. Upload the candidate to App 851's **Working Draft** and verify in Developer Console that the expected App version, bundled Executa version, and bundle are present.
4. Switch to App **382**'s own Anna credentials. Repeat the same identity checks, explicitly confirming App ID **382** and Executa ID/tool ID **1164 / tool-rinat-verigate-authority-2um8gwhw**.
5. Upload the **same** candidate to App 382's **Working Draft** and verify its version and bundle.
6. Do not mark the release complete until both Developer Console pages show the same candidate version and the expected account-specific Executa mapping. Record each account's result separately.

If the active credential, App ID, Executa ID, or tool ID is ambiguous or mismatched, stop before `apps push`. Do not guess, silently fall back to the other account, or change identity metadata manually. Use a separate account-specific identity cache for each target.

## Release boundary

- The normal release upload is a **Working Draft update** on both accounts.
- Do not run `apps cut`, immutable publish, `apps submit-review`, or Marketplace publication unless the owner explicitly requests that next step.
- Preserve existing immutable versions and review-pinned candidates. Updating a Working Draft must not replace or resubmit a version already in review.
- Do not use `--skip-executa-publish` unless the matching account's Executa already has the exact candidate version and has been verified in that account.
- A successful push to one account does not satisfy the release requirement. The second account must also be updated and verified.

## Current candidate reference (2026-11-20)

The latest validated candidate recorded for this workflow is **Anna App 0.1.37 / Executa 0.1.23**, from PR [#65](https://github.com/rudimentall1/verigate/pull/65). The implementation commit is `d51bcca071f8c1cacf4b14e6a229515e336744e5`; the PR head is `61f2b8a2d7b7e34f8d0d1a709a6ae807498b09ff`. The four-platform Executa build and full CI were reported passing for that candidate.

**Important branch note:** the `ANNA` branch at checkpoint creation is an older source snapshot (App manifest **0.1.9**, Executa manifest **0.1.8**). This checkpoint records the dual-account release rule; it does not make that old source snapshot the current release candidate. Before uploading, use the exact validated release-candidate commit and artifacts, not the stale manifests on this branch.
