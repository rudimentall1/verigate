# Verigate Authority — Anna Founding Builder submission

**Updated:** 2026-11-09  
**DoraHacks Build:** https://dorahacks.io/build/50393  
**Repository:** https://github.com/rudimentall1/verigate  
**Current Anna package:** App 0.1.28 (Draft) / bundled Executa 0.1.16

> **Positioning:** User-controlled payments for AI agents inside Anna. Anna understands the request. Verigate decides whether it is authorized. The user stays in control of the wallet.

---

## DoraHacks listing fields

### Project title

**Verigate Authority — Safe AI-Agent Payments on Anna**

### Short description

**Anna AI interprets payment requests; Verigate independently enforces user-approved limits before a supported wallet hand-off.**

### Category and tags

- **Category:** Crypto / Web3
- **Primary tags:** AI, AI Agents, Security, Payments, Developer Tools, ANNA
- Keep LLM only if the tag picker supports it. Do not add tags for capabilities that are not implemented.

### Primary video

Use the Anna-facing explainer first:

https://github.com/rudimentall1/verigate/blob/main/docs/media/verigate-explainer.mp4

Use the technical proof demo as a secondary link:

https://github.com/rudimentall1/verigate/blob/main/docs/media/verigate-demo.mp4

The first video should introduce the Anna user workflow. The terminal proof is supporting technical evidence, not a substitute for showing the Anna App.

---

## Full project description — paste into DoraHacks Details

### The problem

AI agents are moving from answering questions to taking actions for users. In Anna, that can include preparing payments and working with connected tools. But a language model should not be the component that decides whether money may move.

A model can misunderstand a payment request, extract the wrong recipient, miss a malicious instruction, or produce a plausible action outside the user's limits. Asking the model to “be careful” is not an authorization system.

### What Verigate does

**Verigate Authority adds an independent authorization step to an AI-assisted payment flow in Anna.**

The user describes a payment in ordinary language. Anna's host LLM interprets the request, extracts the payment fields, asks for missing or ambiguous details, and provides contextual risk findings. The model is advisory: it cannot issue permission, turn a BLOCK into an approval, or lower a deterministic policy decision. If Anna Sampling is unavailable, the App clearly labels a conservative policy-only preview; it does not pretend that AI review ran, and that degraded path cannot issue execution authority.

Verigate's deterministic policy engine checks the explicit payment details and the installation's current authority state. It validates the recipient for the selected network and evaluates the asset, network, amount, recipient history, spending controls, review thresholds, and rate limits. It returns a signed **ALLOW**, **WARN**, or **BLOCK** decision.

The user sees the exact payment details before authorization:

1. **Interpret:** Anna's host LLM extracts the amount, asset, network, recipient, and payment context. Missing or ambiguous fields stop the flow until they are resolved.
2. **Decide:** Verigate evaluates the normalized payment against deterministic policy. AI risk findings can make an otherwise eligible result stricter by escalating ALLOW to WARN; they cannot authorize a payment or override BLOCK.
3. **Confirm:** The user explicitly confirms the exact payment in the Anna App. A WARN requires a separate review of the exact matched warnings. BLOCK is never overridable.
4. **Authorize:** Verigate issues a short-lived, one-time Ed25519 Execution Authorization bound to the exact payment action, including its network, token, recipient, amount, capability, and policy context.
5. **Enforce:** Before wallet hand-off, Verigate ExecutionRouter verifies and consumes the authorization. A replay or a changed transaction is rejected. A consumed permission cannot be reused.
6. **Hand off:** For native USDC on Base and Ethereum, the App can pass the exact authorized transaction to an injected EIP-1193 wallet provider when the Anna session exposes one. The wallet—not Anna or Verigate—holds the private keys and signs the transaction.

**The model interprets. Verigate enforces authority. The user controls the wallet.**

### Why this matters to Anna

Anna provides the host LLM, App runtime, and user-facing application environment. Verigate adds a missing control between an agent's interpretation and a consequential action.

This makes the payment experience more than a chatbot that promises to follow instructions. Users get explicit limits, a review step for warnings, a permission bound to the exact action, replay protection at the supported execution boundary, and a signed decision record.

For Anna's ecosystem, the goal is practical: make it safer for users to delegate payment preparation to AI without asking them to trust the model with unrestricted authority.

The Anna integration uses a bundled Python Executa and Anna's protocol-v2 reverse Sampling interface. The App does not store a third-party model-provider API key. Anna's host LLM performs interpretation and contextual review; Verigate's own deterministic policy remains the authority source.

### What is implemented

- Anna App UI with a bundled Verigate Python Executa.
- Natural-language payment interpretation through Anna host LLM Sampling, with clarification for missing or ambiguous details.
- Deterministic ALLOW / WARN / BLOCK policy decisions and signed Ed25519 Decision Receipts.
- Network-aware recipient-address validation.
- Transaction limits, first-recipient limits, rolling 24-hour authorization-budget controls, review thresholds, and rate limits.
- Separate user confirmation for authorization; WARN requires an additional exact-warning review.
- Short-lived, one-time Execution Authorization bound to the exact payment action.
- App-scoped, one-time confirmation gates; direct chat/tool calls cannot create the required user approval.
- ExecutionRouter verification and fail-closed permission consumption before wallet hand-off.
- Native USDC wallet hand-off code for Base and Ethereum, subject to wallet-provider availability in the Anna session.
- Solana policy checks and signed authorization; Solana wallet submission is not included in this Anna App release.
- Public source code, threat model, local test harness, and CI evidence.

### Current implementation and test evidence

- **Anna App:** 0.1.28, App ID 851, immutable version ID 2082. Bundle status is ready; platform status is **Draft**, not Marketplace-published and not submitted for review.
- **Bundled Executa:** production version 0.1.16, Executa ID 1314, version ID 1042.
- **Automated tests:** latest recorded full Python suite — **626 passed, 4 skipped**; Anna UI E2E — **61/61 passed**.
- **Continuous integration:** the current main commit `ce1d041e61bc090dab7a4ae98777deda71a7f4ef` completed all three CI jobs successfully: Anna UI, Python tests, and contracts.  
  https://github.com/rudimentall1/verigate/actions/runs/42629586291
- **Executa packaging:** reproducible build and extracted-package smoke tests completed for Windows x86_64, Linux x86_64, macOS ARM64, and macOS Intel x86_64. These are workflow artifacts; Executa 0.1.16 is not represented as a public GitHub Release.  
  https://github.com/rudimentall1/verigate/actions/runs/42571400453
- **Live Anna Runtime evidence:** immutable App versions 0.1.25 and 0.1.26 were tested in the actual Anna Runtime. The tests observed host-LLM interpretation, deterministic policy evaluation, Ed25519 receipt verification, one-time authorization, router consumption, and the MetaMask prompt for a 25 USDC Base transfer. The user cancelled at the wallet prompt because the test wallet was empty. No wallet signature, transaction hash, broadcast, or on-chain settlement occurred. App 0.1.27 added wallet-state lifecycle hardening; App 0.1.28 carries that runtime forward and refreshes listing media only.

### Current limitations — explicit

- App 0.1.28 is still a **Draft**. It has not passed Anna App Review and is not published in the Marketplace.
- Availability of an injected EIP-1193 wallet provider inside a fresh Anna Cloud Agent session remains unverified. Without that provider, policy checks and signed authorizations are available, but the App cannot submit a wallet transaction from that session.
- Native USDC wallet hand-off is limited to Base and Ethereum. Solana wallet submission is not implemented in this App version.
- No successful signed or broadcast payment is claimed. The live test stopped at the MetaMask confirmation prompt.
- The rolling 24-hour Anna budget is based on non-BLOCK authorization records, not chain-confirmed transfers. A wallet rejection or user cancellation does not automatically release the reserved authorization budget.
- Anna's current accounting principal is scoped to one persistent Executa installation. Separate Cloud Agent workspaces or issuer keys are not aggregated into one account-wide budget; cross-Agent aggregation is not implemented.
- The Anna App is an execution-path gate, not a universal firewall for every wallet or external client. Actions that bypass the supported Verigate router are outside this App's enforcement boundary.
- The generic Verigate service is not a hosted multi-tenant product. Production KMS/HSM key custody and key-rotation operations are not shipped.
- The project has not undergone an independent third-party security audit.

### What comes next

1. Complete Anna App Review and verify the full App lifecycle in a fresh Cloud Agent session, including wallet-provider availability and persistence behaviour.
2. Complete a low-value test transaction only in a safe test environment, then add independent chain-observation evidence. A wallet-returned transaction hash alone will not be presented as confirmation or finality.
3. Harden cross-Agent budget accounting with a trusted platform principal and concurrency-safe shared ledger.
4. Publish proof-format conformance vectors and commission an independent security review.
5. Productize the protocol and verifier for other agent platforms after the Anna App is approved and its user workflow is validated.

---

## Reproducible technical evidence

These commands run from the repository root. They demonstrate the underlying authorization protocol; they do not send a real payment.

### 1. Portable proof verification

```bash
python examples/genesis_demo.py
```

Expected: the original portable proof verifies as **VALID**, a tampered proof verifies as **INVALID**, and the command ends with `GENESIS 2.0 DEMO: PASS`.

### 2. Execution-boundary mutation test

```bash
python demo_tamper_enforcement.py
```

Expected: changing the approved tool endpoint or EVM destination after ALLOW returns **BLOCK** and the executor callback is not invoked (**Broadcasts: 0**). The unchanged case uses a local in-process demo callback; it is not a blockchain broadcaster.

### 3. Anna integration test commands

```bash
python -m pytest -q
npm run test:anna-ui
npm run test:atomic
npm run test:guard
cd anna && npx --yes @anna-ai/cli@0.1.64 validate --strict
```

The local Anna UI E2E harness exercises the real App bundle and Python Executa subprocess with a mock Anna Sampling host. It proves the local integration flow; it does **not** prove that a fresh Anna Cloud Agent session exposes the wallet provider or that cloud persistence is correct.

---

## Links for the DoraHacks Build

| Field | Use this current link |
|---|---|
| Source repository | https://github.com/rudimentall1/verigate |
| Anna App source and manifest | https://github.com/rudimentall1/verigate/tree/main/anna |
| Anna integration guide and acceptance evidence | https://github.com/rudimentall1/verigate/blob/main/anna/README.md |
| Judge route | https://github.com/rudimentall1/verigate/blob/main/docs/DORAHACKS-JUDGE-PATH.md |
| Threat model | https://github.com/rudimentall1/verigate/blob/main/docs/threat-model.md |
| Privacy policy | https://github.com/rudimentall1/verigate/blob/main/PRIVACY.md |
| Portable proof specification | https://github.com/rudimentall1/verigate/blob/main/docs/verigate-authority-proof-v1.md |
| Anna-facing explainer | https://github.com/rudimentall1/verigate/blob/main/docs/media/verigate-explainer.mp4 |
| Technical proof demo | https://github.com/rudimentall1/verigate/blob/main/docs/media/verigate-demo.mp4 |
| Latest main CI (3/3 jobs) | https://github.com/rudimentall1/verigate/actions/runs/42629586291 |
| Four-platform Executa build evidence | https://github.com/rudimentall1/verigate/actions/runs/42571400453 |
| Offline verifier package | https://pypi.org/project/verigate-verify/ |

## Replace the stale fields on the existing Build page

Remove these old references:

- App 0.1.12 and Executa 0.1.11 — current package is App 0.1.28 Draft / Executa 0.1.16.
- The `ANNA/anna` branch URL — use `https://github.com/rudimentall1/verigate/tree/main/anna`.
- PR #16 as the current Anna integration source — use the current `main/anna` tree and `anna/README.md`.
- Release `anna-verigate-authority-v0.1.8` — it is historical and is not the current Executa version. Do not substitute a fabricated 0.1.16 release; use the verified build workflow link above.
- The old claim of 493 tests and 21 Anna UI E2E tests — current recorded results are 626 passed / 4 skipped and 61/61 Anna UI E2E.
- Any wording that implies a successful wallet payment, a transaction hash, or on-chain settlement.
- Any statement that the App is published or has qualified for Founding Builder status.

Keep the team size at one and do not invent partners, users, customers, audits, or marketplace approval.

---

## Founding Builder program readiness — operator note, not listing copy

The Anna Founding Builder Program is **not a Top-3 winner-takes-all judging contest**. According to the official rules, qualification requires an approved and Marketplace-published App plus at least **200 Qualified App MAU in one calendar month** during the September 1–November 30, 2026 qualification window. A Qualified App Run must be initiated by a signed-in Anna user, complete the App's primary function, and return a meaningful result. Developer/QA accounts, failed or cancelled runs, bots, and artificial usage do not count.

As of 2026-11-09, Verigate's App is still Draft and has no evidenced Qualified App MAU. Therefore **Verigate is not yet qualified**. The immediate business bottleneck is Marketplace approval and genuine user adoption, not more protocol features or a more aggressive prize claim.

Program rules were updated on October 4: from the October measurement cycle, Apps belonging to the same Builder are measured as one portfolio, with users deduplicated across those Apps and a maximum of one Builder grant per month. The advertised $80,000 is the total monthly Builder Grant pool, not an individual prize.

Official rules:  
https://forum.anna.partners/t/turn-your-ai-agents-apps-into-recurring-monthly-grants-join-the-anna-ai-os-founding-builder-program-up-to-80k-month-pool/205

**Portal boundary:** this document is the canonical, paste-ready replacement for DoraHacks Build #50393. Updating GitHub does not edit the separately hosted DoraHacks page. The page fields, media, and links must still be changed through its **Edit** form.
