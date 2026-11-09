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

The current Anna platform draft is App **0.1.27** (App ID 851, version ID 2078) with bundled production Executa **0.1.16** (Executa ID 1314, version ID 1042). App 0.1.27 hardens wallet-authorization UI state: consumed permissions are reflected immediately, stale authorization state is cleared before renewal, and a lost/malformed consume response is treated as an unknown outcome rather than as proof that the permission remains unused.

The latest recorded local verification is 626 Python tests passed / 4 skipped and 61/61 Anna UI E2E tests. GitHub CI completed all three jobs successfully on source commit `fe3cbd99db24eee8e13237467f11b6122abc124a`. The four-platform Executa 0.1.16 reproducible build and extracted-package smoke tests also passed for Windows x86_64, Linux x86_64, macOS ARM64 and macOS Intel x86_64.

## Current status and limitations

- Anna App 0.1.27 is an immutable **draft**. It is not Marketplace-published and has not been submitted for review.
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
- **Latest source CI (3/3 jobs):** https://github.com/rudimentall1/verigate/actions/runs/42596367889
- **Four-platform Executa 0.1.16 build evidence:** https://github.com/rudimentall1/verigate/actions/runs/42571400453
- **Privacy policy:** https://github.com/rudimentall1/verigate/blob/main/PRIVACY.md
- **Threat model:** https://github.com/rudimentall1/verigate/blob/main/docs/threat-model.md
- **Latest public tagged Executa release (historical 0.1.12):** https://github.com/rudimentall1/verigate/releases/tag/anna-verigate-authority-v0.1.12

## Listing media

The Anna manifest now references the checked-in listing assets through the canonical `main` path rather than the old pinned commit `471a9f6`. The current screenshot filenames still carry the `v019` prefix and their image contents have not been recaptured for App 0.1.27. Do not describe those images as fresh 0.1.27 screenshots; replace them only after capturing the actual current Runtime UI.
