# Verigate Authority - DoraHacks submission copy

**Updated:** 2026-11-09
**Canonical source:** https://github.com/rudimentall1/verigate
**DoraHacks listing/link-refresh merge commit:** 45cfc4c107949756fdf2acd2d36423f9721db1bd

> This is the canonical replacement copy for the external DoraHacks project page. Pushing this file updates the repository only; it does not edit the DoraHacks website record.

## DoraHacks listing fields

**Project title**

Verigate Authority

**Short description**

Deterministic authorization for AI-agent payments: Anna AI interprets; Verigate enforces policy and one-time wallet permissions.

**Category and tags**

Crypto / Web3
AI, LLM, ANNA, AI Agents, Developer Tools

**Project description**

AI agents can request payments. They must not authorize themselves.

An agent can misunderstand a request, follow malicious instructions or send funds to the wrong recipient. Verigate places an independent authorization check between the agent and the wallet.

Verigate Authority is an authorization layer integrated into Anna. The user describes a payment in ordinary language. Anna's host LLM interprets the request, extracts the recipient, amount, asset, network and purpose, asks for missing or ambiguous details, and provides a separate contextual risk review. That model output is advisory only.

Verigate's deterministic policy engine makes the final **ALLOW / WARN / BLOCK** decision. AI findings can make a result stricter, but the model cannot create execution authority or turn a policy denial into approval. Each decision is returned in an Ed25519-signed Decision Receipt, verified by the App before display.

A user must explicitly confirm the exact payment in the App before Verigate issues a short-lived, one-time Execution Authorization. The permission binds the exact action, including recipient, asset, network, amount, resource and transaction envelope. A separate short-lived App-scoped approval is required before wallet hand-off. Verigate ExecutionRouter verifies and consumes the one-time permission before the connected wallet is asked to sign.

The wallet keeps its private keys. Anna and Verigate do not custody funds. The implemented wallet hand-off is limited to native USDC on Base and Ethereum. Solana currently supports policy checks and signed authorization artifacts, but not wallet transaction submission in this App.

**The AI proposes. Verigate checks authority. The user remains in control of the wallet.**

## What has been demonstrated

Live Anna Runtime testing confirmed:
- Anna host LLM interpretation and a separate contextual risk review for a natural-language payment request.
- Deterministic ALLOW and successful Ed25519 Decision Receipt verification.
- Explicit user confirmation followed by an Ed25519-verified, exact-action, one-time Execution Authorization.
- ExecutionRouter consumption before the connected wallet was opened.
- MetaMask displayed the expected 25 USDC Base transfer to the authorized recipient. The user intentionally cancelled the wallet signature because the test wallet had no funds; **no transaction hash, broadcast or on-chain payment occurred**.

The current Anna platform draft is App **0.1.28** (App ID 851, version ID **2082**) with bundled production Executa **0.1.16** (Executa ID **1314**, version ID **1042**). App 0.1.28 is a listing/metadata refresh of the 0.1.27 runtime: it retains wallet-authorization lifecycle hardening and changes no runtime or policy behavior. The App bundle is ready (3 files, 91,055 bytes; content hash 67f237c123a07e6c09900acd5fe5238c60e96b43ccf8ff8ea4b14e0826b6bec6).

The latest recorded full Python suite is **626 passed / 4 skipped**; the Anna UI E2E suite is **61/61**. The DoraHacks listing/link-refresh merge commit 45cfc4c107949756fdf2acd2d36423f9721db1bd passed all three main-branch GitHub Actions jobs ([CI run 42623793063](https://github.com/rudimentall1/verigate/actions/runs/42623793063)). The four-platform Executa 0.1.16 reproducible build and extracted-package smoke tests also passed for Windows x86_64, Linux x86_64, macOS ARM64 and macOS Intel x86_64 ([build run 42571400453](https://github.com/rudimentall1/verigate/actions/runs/42571400453)).

## Current status and limitations

- Anna App 0.1.28 is an immutable **draft** (published_at=null, is_published=false, review_candidate_version=null). It is not Marketplace-published and has not been submitted for review.
- Executa 0.1.16 has successful four-platform workflow build artifacts, but **no public GitHub Release has been created for 0.1.16**. Do not present the older 0.1.8 or 0.1.12 release as the current bundled Executa.
- No successful wallet signature, transaction broadcast, on-chain inclusion, finality or reorg handling is claimed.
- A separately governed production CHAIN_VERIFIER is not integrated into the normal Anna UI flow.
- Cloud workspace durability across a real restart/reinstall and a live App-scope replay attempt remain unverified.
- Verigate is an execution-path authorization gate, not a universal firewall for every wallet/client. Independent security audit, hosted multi-tenant service, and KMS/HSM key custody are not claimed.

## Current links for the DoraHacks listing

| Listing field | Use this current URL |
|---|---|
| Source repository | https://github.com/rudimentall1/verigate |
| Anna integration directory | https://github.com/rudimentall1/verigate/tree/main/anna |
| Anna integration and runtime evidence | https://github.com/rudimentall1/verigate/blob/main/anna/README.md |
| Explainer video | https://github.com/rudimentall1/verigate/blob/main/docs/media/verigate-explainer.mp4 |
| Technical demo video | https://github.com/rudimentall1/verigate/blob/main/docs/media/verigate-demo.mp4 |
| Current source CI (3/3) | https://github.com/rudimentall1/verigate/actions/runs/42623793063 |
| Four-platform Executa 0.1.16 build evidence | https://github.com/rudimentall1/verigate/actions/runs/42571400453 |
| Privacy policy | https://github.com/rudimentall1/verigate/blob/main/PRIVACY.md |
| Threat model | https://github.com/rudimentall1/verigate/blob/main/docs/threat-model.md |
| DoraHacks listing/link-refresh merge commit | https://github.com/rudimentall1/verigate/commit/45cfc4c107949756fdf2acd2d36423f9721db1bd |

**Release link policy:** use the four-platform build evidence for Executa 0.1.16. The latest public tagged release remains 0.1.12 and is not the version bundled by the current App. No public 0.1.16 GitHub release exists yet.

## Current listing media

The Anna manifest uses one cover and five current screenshots from the live 0.1.27 Runtime. These links point to main, not to a commit-specific snapshot:

| Asset | URL |
|---|---|
| Cover | https://raw.githubusercontent.com/rudimentall1/verigate/main/anna/assets/listing/00-cover.jpg |
| ALLOW | https://raw.githubusercontent.com/rudimentall1/verigate/main/anna/assets/listing/v027-1-allow-base-usdc.png |
| WARN / human review | https://raw.githubusercontent.com/rudimentall1/verigate/main/anna/assets/listing/v027-2-warn-human-review.png |
| Hard-cap BLOCK | https://raw.githubusercontent.com/rudimentall1/verigate/main/anna/assets/listing/v027-3-block-transaction-cap.png |
| Missing amount | https://raw.githubusercontent.com/rudimentall1/verigate/main/anna/assets/listing/v027-4-missing-amount.png |
| One-time permission ready | https://raw.githubusercontent.com/rudimentall1/verigate/main/anna/assets/listing/v027-5-one-time-permission-ready.png |

The fifth image is a permission-ready state and deliberately shows "Not consumed"; it is not presented as a completed wallet submission or confirmed payment.

## Replacements for the old DoraHacks card

| Old card entry | Replace it with |
|---|---|
| Raw asset URLs pinned to commit 471a9f634f6e57d6d84adeddd6646fb9cd277388 | The six raw.githubusercontent.com/.../main/anna/assets/listing/ URLs listed above |
| v019-1-allow.png, v019-4-risk-flag-warn.png, v019-2-block-invalid-recipient.png, v019-3-missing-details.png | The five v027 Runtime screenshots listed above |
| https://github.com/rudimentall1/verigate/tree/ANNA/anna | https://github.com/rudimentall1/verigate/tree/main/anna |
| https://github.com/rudimentall1/verigate/pull/16 | https://github.com/rudimentall1/verigate/blob/main/anna/README.md (current integration guide; PR #16 is still an old open PR, not the current source snapshot) |
| https://github.com/rudimentall1/verigate/releases/tag/anna-verigate-authority-v0.1.8 | https://github.com/rudimentall1/verigate/actions/runs/42571400453 (current four-platform Executa 0.1.16 build evidence; not a public release) |
| Anna App 0.1.12 / Executa 0.1.11 | Anna App 0.1.28 Draft / bundled Executa 0.1.16 |
| 493 automated tests / 21 Anna UI tests | 626 Python tests passed, 4 skipped / Anna UI E2E 61/61 |
| Generic claim that wallet submission is verified | State precisely: live wallet hand-off reached MetaMask; user cancelled because the test wallet was empty; no signature, transaction hash or broadcast occurred |

The six current image URLs were checked from the laptop on 2026-11-09 and returned HTTP 200 with the expected JPEG/PNG content types. docs/media/verigate-explainer.mp4, the repository directory links, privacy policy and source repository are present in the current main tree.

**External portal boundary:** this document and the GitHub links are updated in the repository. The DoraHacks project-page fields themselves are stored by DoraHacks and must be replaced on that website; a GitHub commit cannot edit the external listing.