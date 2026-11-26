# Hackathon submission — Verigate

## Project name

**Verigate — Authorization Infrastructure for AI Agents**

## Tagline

**Let agents act. Keep authority outside the model.**

## Description

AI agents are moving beyond chat. They can initiate payments, call business APIs, modify systems and trigger actions that are difficult to reverse. Giving an agent broad credentials and relying on prompt instructions is not an adequate security model. A model can misunderstand a request, follow malicious instructions or simply make a mistake.

Verigate adds an independent authorization layer between an agent and the action it wants to perform.

A person or organization defines the authority that may be delegated. The agent proposes an exact action. Verigate checks the agent identity, capabilities, policy constraints and relevant context independently of the model. If the action is permitted, Verigate issues a signed, one-time authorization bound to that specific action. The supported execution boundary verifies the authorization before allowing the side effect. A changed destination, altered action or reused permission is rejected.

The result is more than a risk score or an approval prompt. Verigate makes authority explicit, enforces it at the execution boundary and produces portable evidence that a third party can verify independently.

## How it works

1. **Delegate bounded authority.** A person or organization defines what an agent may do, within which limits and when human approval is required.
2. **Receive an action proposal.** An agent or application submits the exact action it wants to perform.
3. **Evaluate authority independently.** Verigate checks identity, capabilities, deterministic policy and relevant evidence. The AI model cannot override the decision.
4. **Authorize one exact action.** An allowed request receives a signed, short-lived, one-time execution authorization.
5. **Enforce before execution.** The supported adapter verifies the authorization and rejects tampered or replayed requests before the side effect.
6. **Verify the evidence.** Verigate exports a portable proof that can be checked offline with the issuer's public key.

## Why Anna is part of the project

Anna is the first human-facing integration of Verigate. It lets a person express a payment intent, review the policy result and complete explicit approval steps where required. Anna's host AI can help interpret a request and provide contextual risk signals, but it does not grant authority and cannot override Verigate's deterministic decision.

Anna is an interface, not the security boundary. Developers can integrate agents and applications directly with Verigate through its API and SDK without using Anna.

## What is built

- Open-source authorization protocol and deterministic policy engine.
- Agent identity and capability controls, signed action-bound authorization and one-time execution enforcement.
- Runnable end-to-end authority lifecycle and tamper demonstrations.
- Portable proof format and standalone offline verifier.
- External-agent quickstart and runnable integration example.
- Anna App integration demonstrating human-facing payment delegation and a connected-wallet hand-off path for Base and Ethereum.

## Evidence and current status

- The latest `main` CI run completed successfully across all four jobs: **662 Python tests passed**, **64/64 Anna UI end-to-end tests passed**, contract tests, container/API-auth checks, strict Anna schema-4 validation and Linux Executa 0.1.18 build/smoke: [CI run](https://github.com/rudimentall1/verigate/actions/runs/43179226473), on commit `9f7b2e4c5d052fd37839ad14a0799243a56bc14d`.
- Four-platform Executa 0.1.18 reproducible builds, extracted-package smoke tests and SHA-256 verification passed for Linux x86_64, Windows x86_64, macOS ARM64 and macOS Intel: [build run](https://github.com/rudimentall1/verigate/actions/runs/42989643581). The workflow artifacts were independently inspected; the GitHub Release step was intentionally skipped.
- The current Anna Console cut is **App 0.1.31** with bundled **Executa 0.1.18**. It remains a Draft and has not been submitted for Marketplace review or publication.
- A live Cloud Agent invocation was verified with the previous App 0.1.30 / Executa 0.1.17 combination. A fresh live invocation of 0.1.18 is not yet verified.
- One **0.000001 USDC** transfer on Base was submitted through the Anna App and independently checked through Base RPC. This is a single successful micro-transfer, not evidence of broad production readiness.
- Verigate is an open-source protocol implementation and integration project, not a hosted multi-tenant production service. No independent third-party security audit or production KMS/HSM key custody is claimed.

## Links

- Repository: https://github.com/rudimentall1/verigate
- Product architecture: https://github.com/rudimentall1/verigate/blob/main/docs/PRODUCT-ARCHITECTURE.md
- Anna integration: https://github.com/rudimentall1/verigate/tree/main/anna
- Anna documentation: https://github.com/rudimentall1/verigate/blob/main/anna/README.md
- Anna release status: https://github.com/rudimentall1/verigate/blob/main/anna/docs/RELEASE-STATUS.md
- External agent quickstart: https://github.com/rudimentall1/verigate/blob/main/docs/EXTERNAL_AGENT_QUICKSTART.md

## Team

Rinat Nabiev — Founder / Developer

GitHub: https://github.com/rudimentall1
X: https://x.com/OWNERAGET
