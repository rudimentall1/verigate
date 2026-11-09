# Verigate Authority — DoraHacks judge-first submission

**Updated:** 2026-11-09
**DoraHacks Build:** https://dorahacks.io/build/50393
**Canonical repository:** https://github.com/rudimentall1/verigate
**Product integration:** Anna App 0.1.28 Draft / bundled Executa 0.1.16

## Project title

**Verigate Authority — AI Agents Can Act. They Cannot Self-Authorize.**

## Short description

AI agents can propose payments. Verigate enforces exact-action permissions before execution and makes the proof independently verifiable.

## Recommended DoraHacks Build metadata

- **Category:** Crypto / Web3
- **Tags:** AI, LLM, AI Agents, Developer Tools, Security, Payments, Infrastructure. Keep ANNA as an integration tag if it is available in the tag picker.
- **Primary Demo Video field:** use the technical proof video, docs/media/verigate-demo.mp4. Keep docs/media/verigate-explainer.mp4 as the secondary overview link.
- **Team:** keep the actual one-member team size shown on the current Build page; describe only real responsibilities and do not add unconfirmed partners or advisors.
## The 15-second pitch

AI agents should be able to act, but they must never be able to grant themselves permission to act. Verigate places a deterministic, cryptographic authority boundary between an agent and execution. It checks who is acting, what they are allowed to do, and the exact action being requested. A changed destination or tampered proof is rejected — not merely flagged by another AI model.

## Why this matters to a hackathon organizer, sponsor, or judge

When a hackathon rewards autonomous agents, a successful task demo is not enough. The important question is: **what proves the agent was authorized to perform that exact action, and what stops the action if its destination changes after approval?**

Most demos show that an agent can complete a task. Verigate makes the permission boundary itself testable:

- Change a tool endpoint after ALLOW → BLOCK; execution callback is not invoked (Broadcasts: 0).
- Change an EVM transaction destination after ALLOW → BLOCK; execution callback is not invoked (Broadcasts: 0).
- Verify the original portable proof offline → VALID.
- Alter the proof package → INVALID.

This gives judges a repeatable security test instead of asking them to trust a prompt, a screenshot, or the model's claim that it behaved safely.

## Project description

AI agents are moving from answering questions to requesting payments and invoking privileged tools. That creates a control problem: an agent can misunderstand a request, be manipulated by hostile instructions, or attempt an action outside its authority. A model's confidence is not permission.

**Verigate is an independent authority control plane for agentic execution.** The model may interpret a request and provide advisory risk findings, but it is not the source of execution authority.

Verigate evaluates the exact action against deterministic identity, capability, policy, context, and limit constraints. It returns ALLOW, WARN, or BLOCK. Signed policy versions and Ed25519 Decision Receipts make the decision auditable. A short-lived, one-time Execution Authorization binds the approved action to its exact fingerprint. The execution router verifies and consumes that permission fail-closed before it invokes the executor. A mutation to the target, resource, tool endpoint, or transaction envelope changes the action fingerprint and is rejected.

The exported authority proof is separate from the runtime. A third party can verify its integrity, trust anchor, issuer signature, authorization, execution, outcome, and historical authority without trusting the running Verigate service. Tampering with the proof makes independent verification return INVALID.

**Anna is the natural-language product integration.** A user describes a payment; Anna's host LLM extracts the details and provides contextual risk review. That review is advisory. Verigate's deterministic policy engine owns the ALLOW / WARN / BLOCK decision. In the Anna wallet flow, the user separately confirms the exact payment before a one-time permission is issued and consumed through ExecutionRouter before the wallet is asked to sign.

Verigate is not another wallet, another LLM, or a prompt-based safety layer. It is the authority and evidence layer beneath an agent that is allowed to take consequential actions.

## How it works

1. **Interpret:** the agent or Anna interface turns a natural-language request into an explicit action intent. In the Anna integration, the host LLM can ask for missing details and add advisory contextual flags.
2. **Decide:** deterministic policy checks identity, capability, target, resource, asset, network, amount, limits, and applicable constraints. The model cannot approve an action or lower a policy decision.
3. **Authorize:** only an eligible decision can produce a signed, short-lived permission bound to the exact action and current authority state. The Anna wallet flow requires a separate user confirmation.
4. **Enforce:** the execution router verifies and consumes the one-time permission before dispatch. Replay or any mutation of the authorized action is rejected.
5. **Prove:** portable evidence can be verified independently offline. Altering the evidence is detected.

## What judges can verify in under two minutes

The repository contains two runnable, deterministic demonstrations. They require no funded wallet and do not broadcast a real transaction.

**1. Full authority lifecycle and offline proof**

    python examples/genesis_demo.py

The command runs the Genesis 2.0 lifecycle contract, verifies the checked-in proof package with the standalone verifier (RESULT: VALID), modifies the package, and requires the verifier to return RESULT: INVALID. The command exits non-zero if either proof check fails.

**2. Adversarial execution-boundary test**

    python demo_tamper_enforcement.py

The command creates a temporary issuer key and database, issues a signed authorization, then changes the tool endpoint and transaction destination after approval. Both mutations return VERIGATE: BLOCK and Broadcasts: 0. The untampered case invokes a local demo callback and returns demo-tx-hash; this is a test callback, **not a blockchain transaction**.

**3. See the user-facing integration**

Open the Anna integration guide and its live Runtime acceptance evidence:

- https://github.com/rudimentall1/verigate/blob/main/anna/README.md
- https://github.com/rudimentall1/verigate/blob/main/docs/ANNA-RELEASE-GATE.md

The Anna UI screenshots show the real Runtime states. The final permission-ready screenshot says NOT CONSUMED; it is not represented as a completed payment.

## What is working today

- **Genesis 2.0 authority lifecycle:** identity/capability-scoped action authorization, execution, outcome, dynamic-authority update, and a portable proof.
- **Deterministic execution enforcement:** exact-action binding, one-time authorization consumption, and fail-closed rejection of endpoint or transaction mutations.
- **Independent proof verification:** standalone offline verifier and the verigate-verify package on PyPI.
- **Adversarial verification:** mutation corpus and runnable tamper demonstrations.
- **Signed policy lineage and governance:** signed policy versions, governed policy publication, freeze/rollback, and role-separated quorum controls are implemented in the repository.
- **Anna integration:** current Anna platform draft is App 0.1.28 / Executa 0.1.16. Live Runtime tests on immutable App versions 0.1.25 and 0.1.26 demonstrated LLM interpretation, advisory contextual review, deterministic ALLOW, Ed25519 Decision Receipt verification, one-time Execution Authorization, ExecutionRouter consumption, and hand-off to the connected wallet prompt. App 0.1.27 introduced wallet-state lifecycle hardening; 0.1.28 carries that runtime forward and refreshes listing media only.
- **Test evidence:** 626 Python tests passed, 4 skipped; Anna UI E2E 61/61 passed. The latest main head 2657eb0334dbfef7799c1dee190e5fa7af161d27 passed all three GitHub Actions jobs (anna-ui, test, contracts): https://github.com/rudimentall1/verigate/actions/runs/42624530607. A reproducible four-platform Executa 0.1.16 build/package/smoke workflow passed for Windows x86_64, Linux x86_64, macOS ARM64, and macOS Intel x86_64.

## Product and commercial relevance

**Who would use it:** agent-platform developers, wallet and payment infrastructure teams, and enterprises that allow AI agents to spend funds or invoke privileged tools.

**Why they would integrate it:** Verigate separates the agent's reasoning from the authority to execute. The integration provides deterministic policy enforcement, exact-action one-time permissions, and portable evidence that an external reviewer can verify. It can sit below different agent interfaces instead of requiring every model or application to invent its own authorization mechanism.

**Commercial path:** an integration SDK and verifier for agent platforms and wallet/payment providers, followed by managed policy, governance, and multi-tenant evidence infrastructure for enterprise deployments. The standalone verifier is available; the hosted multi-tenant service is not yet shipped.

## Current state and honest limitations

- Anna App **0.1.28** (App ID 851, version ID 2082) is an immutable **Draft**. It is not Marketplace-published and has not been submitted for review.
- The bundled production Executa is **0.1.16** (Executa ID 1314, version ID 1042). Four-platform workflow artifacts exist, but there is no public GitHub Release for Executa 0.1.16.
- The live Anna wallet test reached the MetaMask confirmation prompt for 25 USDC on Base. The user cancelled because the test wallet was empty. **No wallet signature, transaction hash, broadcast, on-chain inclusion, or payment settlement is claimed.**
- The demo_tamper_enforcement.py callback is a local test callback, not an on-chain broadcaster.
- Solana wallet submission is not part of the current Anna App flow. The Anna wallet hand-off is implemented for native USDC on Base and Ethereum; the recorded live prompt test was on Base.
- The current app is an execution-path authorization gate, not a universal firewall for every wallet, browser, or arbitrary subprocess.
- Verigate is not a hosted multi-tenant service. Production KMS/HSM key custody and key-rotation operations are not shipped.
- The project has not undergone an independent third-party security audit.

## Milestones and roadmap

**Completed and evidenced**
- Core authority lifecycle and portable proof: original proof verifies VALID; modified proof verifies INVALID.
- Adversarial execution boundary: changing the approved tool endpoint or EVM destination after ALLOW returns BLOCK and the local executor callback is not invoked.
- Anna integration: natural-language interpretation, advisory AI review, deterministic policy, signed receipt, one-time authorization, and router consumption were observed in live Anna Runtime tests through the wallet prompt.

**Not yet completed**
- A funded-wallet signature and successful on-chain payment with transaction hash and confirmation evidence.
- Independent third-party security audit and external conformance review.
- Hosted multi-tenant control plane with production KMS/HSM key custody.

**Next milestones**
1. Complete a funded, low-value test transaction with a documented transaction hash, receipt, and chain-observation evidence; keep the demo isolated from production funds.
2. Add independently signed chain outcome attestations and explicit finality/reorg handling.
3. Publish proof-format conformance vectors and commission an independent security review.
4. Productize the SDK/verifier integration for wallet and agent-platform partners; only then expand to a hosted multi-tenant enterprise service.
## Judging fit

| Common judging dimension | Verifiable evidence |
|---|---|
| Innovation / Wow Factor | Authority is outside the model; the model cannot approve itself. A modified exact action is rejected at the execution boundary. |
| Profile completion | Public repository, judge route, demo videos, milestones, roadmap, privacy policy, threat model, proof specification, and test/build evidence. |
| Technical depth / Code quality | Deterministic policy, identity and capability bindings, Ed25519-signed artifacts, one-time consumption, proof format, standalone verifier, and automated test suites. |
| Alignment with Track Requirements | Best fit is a track explicitly covering AI agents, agent security, autonomous payments, wallet infrastructure, or execution middleware. Select only a track whose published requirements this build actually satisfies. |
| Business feasibility | SDK/verifier entry point and clear B2B integration buyers; hosted multi-tenant operations remain roadmap, not a shipped service. |
| Presentation / Completeness | Two reproducible command-line demos, current Anna integration evidence, threat model, proof specification, and build/test evidence. |

## DoraHacks listing links — replace the old card URLs

**Use the technical proof video as the primary Demo Video:**

https://github.com/rudimentall1/verigate/blob/main/docs/media/verigate-demo.mp4

**Keep the explainer as the secondary overview:**

https://github.com/rudimentall1/verigate/blob/main/docs/media/verigate-explainer.mp4

| Field | Current URL |
|---|---|
| Source repository | https://github.com/rudimentall1/verigate |
| README / quick start | https://github.com/rudimentall1/verigate/blob/main/README.md |
| Judge route | https://github.com/rudimentall1/verigate/blob/main/docs/DORAHACKS-JUDGE-PATH.md |
| 3-minute video storyboard | https://github.com/rudimentall1/verigate/blob/main/docs/DORAHACKS-VIDEO-SCRIPT.md |
| Anna integration and runtime evidence | https://github.com/rudimentall1/verigate/blob/main/anna/README.md |
| Anna integration source | https://github.com/rudimentall1/verigate/tree/main/anna |
| Threat model | https://github.com/rudimentall1/verigate/blob/main/docs/threat-model.md |
| Portable proof specification | https://github.com/rudimentall1/verigate/blob/main/docs/verigate-authority-proof-v1.md |
| Privacy policy | https://github.com/rudimentall1/verigate/blob/main/PRIVACY.md |
| Four-platform Executa 0.1.16 build evidence | https://github.com/rudimentall1/verigate/actions/runs/42571400453 |
| Latest main CI (3/3) | https://github.com/rudimentall1/verigate/actions/runs/42624530607 |
| Offline verifier package | https://pypi.org/project/verigate-verify/ |

## Listing media

The Anna manifest references the retained cover and five current Runtime captures:

| Asset | URL |
|---|---|
| Cover | https://raw.githubusercontent.com/rudimentall1/verigate/main/anna/assets/listing/00-cover.jpg |
| ALLOW | https://raw.githubusercontent.com/rudimentall1/verigate/main/anna/assets/listing/v027-1-allow-base-usdc.png |
| WARN / human review | https://raw.githubusercontent.com/rudimentall1/verigate/main/anna/assets/listing/v027-2-warn-human-review.png |
| Hard-cap BLOCK | https://raw.githubusercontent.com/rudimentall1/verigate/main/anna/assets/listing/v027-3-block-transaction-cap.png |
| Missing amount | https://raw.githubusercontent.com/rudimentall1/verigate/main/anna/assets/listing/v027-4-missing-amount.png |
| One-time permission ready | https://raw.githubusercontent.com/rudimentall1/verigate/main/anna/assets/listing/v027-5-one-time-permission-ready.png |

## Remove these stale or misleading entries from the existing DoraHacks page

- Remove the ANNA/anna branch URL; use the main/anna URL above.
- Remove PR #16 as the current integration link. It is an old, still-open PR, not the current source snapshot.
- Remove release anna-verigate-authority-v0.1.8; it is historical and is not the bundled Executa version.
- Remove old copy claiming Anna App 0.1.12 / Executa 0.1.11 and 493 tests / 21 UI tests.
- Replace commit-pinned 471a9f6 and v019 media links with the six current main media URLs above.
- Replace the description's generic claim of completed wallet submission with the precise limitation above: wallet prompt reached, user cancelled, no signature or broadcast.

**Do not claim a guaranteed prize, completed mainnet payment, public release of Executa 0.1.16, hosted production service, or independent security audit.** The advantage is that the implemented controls can be challenged and verified, not that every production condition is already solved.

**Portal boundary:** this file is the canonical paste-ready submission. A commit to GitHub does not edit the separately hosted DoraHacks Build page; the title, summary, details, media, and links must be pasted into that page's Edit form.
