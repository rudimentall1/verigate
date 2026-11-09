# Verigate Authority — DoraHacks submission copy

**Updated:** 2026-11-09  
**Canonical source:** [rudimentall1/verigate](https://github.com/rudimentall1/verigate)

## Short description

A deterministic authorization layer for AI-agent payments. Anna AI interprets the request; Verigate decides authority, signs the decision and gates the exact wallet action.

## Project description

AI agents can request payments. They must not authorize themselves.

An agent can misunderstand a request, follow malicious instructions or send funds to the wrong recipient. Verigate places an independent authorization check between the agent and the wallet.

Verigate Authority is an authorization layer integrated into Anna. The user describes a payment in ordinary language. Anna's host LLM extracts the recipient, amount, asset, network and purpose, asks for missing or ambiguous details, and provides a separate contextual risk review. That model output is advisory only.

Verigate's deterministic policy engine makes the final **ALLOW / WARN / BLOCK** decision. AI findings can make a result stricter, but the model cannot create execution authority or turn a policy denial into approval. Each decision is returned in an Ed25519-signed Decision Receipt, verified by the App before display.

A user must explicitly confirm the exact payment in the App before Verigate issues a short-lived, one-time Execution Authorization. The permission binds the exact action, including recipient, asset, network, amount, resource and transaction envelope. A separate short-lived App-scoped approval is required before wallet hand-off. Verigate ExecutionRouter verifies and consumes the one-time permission before the connected wallet is asked to sign.

The wallet keeps its private keys. Anna and Verigate do not custody funds. The implemented wallet hand-off is limited to native USDC on Base and Ethereum. Solana currently supports policy checks and signed authorization artifacts, but not wallet transaction submission in this App.

## What has been demonstrated

Live Anna Runtime testing confirmed:
- Anna host LLM interpretation and a separate contextual risk review for a natural-language payment request.
- Deterministic ALLOW and successful Ed25519 Decision Receipt verification.
- Explicit user confirmation followed by an Ed25519-verified, exact-action, one-time Execution Authorization.
- ExecutionRouter consumption before the connected wallet was opened.
- MetaMask displayed the expected 25 USDC Base transfer to the authorized recipient. The user intentionally cancelled the wallet signature because the test wallet had no funds; **no transaction hash, broadcast or on-chain payment occurred**.

The current Anna platform draft is App **0.1.28** (App ID 851, version ID **2082**) with bundled production Executa **0.1.16** (Executa ID **1314**, version ID **1042**). App 0.1.28 is a listing/metadata refresh of the 0.1.27 runtime: it retains the wallet-authorization lifecycle hardening, changes no runtime or policy behavior, and uses five current screenshots from the live Anna Runtime. The new App bundle is `ready` (3 files, 91,055 bytes; content hash `67f237c123a07e6c09900acd5fe5238c60e96b43ccf8ff8ea4b14e0826b6bec6`).

The latest recorded full Python suite is 626 passed / 4 skipped; the Anna UI E2E suite is 61/61. The listing-refresh source commit `dbdef40be648391d37bdaa48a5de074474dea2a1` passed all three CI jobs, including strict schema-4 validation, Anna UI E2E and the Linux Executa package smoke test ([CI run](https://github.com/rudimentall1/verigate/actions/runs/42619825112)). The four-platform Executa 0.1.16 reproducible build and extracted-package smoke tests also passed for Windows x86_64, Linux x86_64, macOS ARM64 and macOS Intel x86_64.

## Current status and limitations

- Anna App 0.1.28 is an immutable **draft** (`published_at=null`, `is_published=false`, `review_candidate_version=null`). It is not Marketplace-published and has not been submitted for review.
- The latest public GitHub Executa release is 0.1.12. Executa 0.1.16 has successful four-platform workflow artifacts, but **no public GitHub Release has been created for 0.1.16**.
- No successful wallet signature, transaction broadcast, on-chain inclusion, finality or reorg handling is claimed.
- A separately governed production CHAIN_VERIFIER is not integrated into the normal Anna UI flow.
- Cloud workspace durability across a real restart/reinstall and a live App-scope replay attempt remain unverified.
- Verigate is an execution-path authorization gate, not a universal firewall for every wallet/client. Independent security audit, hosted multi-tenant service, and KMS/HSM key custody are not claimed.

## Links

- **Source repository:** https://github.com/rudimentall1/verigate
- **Anna integration source:** https://github.com/rudimentall1/verigate/tree/main/anna
- **Anna integration and runtime evidence:** https://github.com/rudimentall1/verigate/blob/main/anna/README.md
- **Explainer video:** https://github.com/rudimentall1/verigate/blob/main/docs/media/verigate-explainer.mp4
- **Latest listing-refresh CI (3/3 jobs):** https://github.com/rudimentall1/verigate/actions/runs/42619825112
- **Four-platform Executa 0.1.16 build evidence:** https://github.com/rudimentall1/verigate/actions/runs/42571400453
- **Privacy policy:** https://github.com/rudimentall1/verigate/blob/main/PRIVACY.md
- **Threat model:** https://github.com/rudimentall1/verigate/blob/main/docs/threat-model.md
- **Latest public tagged Executa release (historical 0.1.12):** https://github.com/rudimentall1/verigate/releases/tag/anna-verigate-authority-v0.1.12

## Listing media

The Anna manifest references the current cover and five checked-in `v027` Runtime captures through canonical `raw.githubusercontent.com/.../main/` URLs. The fifth image is a permission-ready state and deliberately shows `Not consumed`; it is not presented as a transaction submission or confirmation. The six URLs were checked from the laptop and each returned HTTP 200.
