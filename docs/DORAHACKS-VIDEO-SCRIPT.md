# Verigate Authority — 3-minute DoraHacks demo video script

**Goal:** make the judge understand the authority problem in the first 10 seconds, then prove the enforcement and evidence claims on screen.

**Primary rule:** show actual terminal output and actual Anna Runtime captures. Do not show a fake successful payment or imply a blockchain broadcast that did not happen.

## 0:00–0:12 — Hook

**Screen:** title card, then a simple flow: AI agent → payment/tool action → wallet/API.

**Voice-over:**

"An AI agent can be smart, useful, and still have too much authority. If it changes a recipient after approval, who stops it? Verigate does. AI agents can propose actions; they cannot authorize themselves."

**On-screen line:** THE MODEL PROPOSES. VERIGATE DECIDES. THE EXECUTION BOUNDARY ENFORCES.

## 0:12–0:35 — The architecture in one view

**Screen:** show the authority flow:

Agent intent → Identity + capability + deterministic policy → Signed one-time authorization → ExecutionRouter → Executor

Then show the separate proof path:

Execution evidence → Portable proof → Independent verifier → VALID / INVALID

**Voice-over:**

"Verigate moves authority outside the model. It checks the principal, capability, policy, limits, and exact action. A signed permission is bound to that action and can be consumed once. A separate verifier checks the evidence without trusting the runtime."

## 0:35–1:05 — Proof that survives leaving the runtime

**Screen:** run the command from the repository root:

    python examples/genesis_demo.py

Show the real output:
- Lifecycle contract: OK
- Independent verifier: RESULT: VALID
- Tampered package: RESULT: INVALID
- GENESIS 2.0 DEMO: PASS

**Voice-over:**

"This is not a screenshot claiming that verification works. The command runs the lifecycle contract, verifies the original portable proof, then modifies the proof package. The independent verifier accepts the original and rejects the altered one."

## 1:05–1:40 — Attack the action, not the prompt

**Screen:** run:

    python demo_tamper_enforcement.py

Highlight these actual output lines:
- Tool endpoint changed after ALLOW → VERIGATE: BLOCK / Broadcasts: 0
- EVM destination changed after ALLOW → VERIGATE: BLOCK / Broadcasts: 0
- Untampered authorization → VERIGATE: ALLOW

**Voice-over:**

"Now we attack the execution boundary. We do not ask the model whether the changed destination looks suspicious. We alter the approved endpoint and transaction destination after authorization. Both are blocked before the executor callback is invoked."

**Required small-print:** "Local deterministic demo callback; no blockchain transaction is broadcast. The unchanged test action returns demo-tx-hash."

## 1:40–2:30 — First user-facing integration: Anna

**Screen:** show actual Anna Runtime captures in this order:
1. Plain-language payment request / extracted details.
2. Anna AI contextual review marked advisory.
3. Deterministic ALLOW / limits.
4. Signed Decision Receipt verified.
5. Exact-action one-time permission.
6. ExecutionRouter consumption and wallet hand-off state.

**Voice-over:**

"Anna is the natural-language interface, not the authority source. Its host LLM interprets the request and can add advisory risk findings. Verigate's deterministic policy makes the decision. The user separately confirms the exact payment; ExecutionRouter consumes the one-time permission before the wallet is asked to sign."

**Required honesty overlay:**

"Live test: 25 USDC on Base reached the MetaMask confirmation prompt. The user cancelled because the test wallet was empty. No signature, transaction hash, broadcast, or on-chain settlement occurred."

Do not show a green 'payment sent' screen, a fabricated transaction hash, or a chain explorer.

## 2:30–2:48 — Why this matters commercially

**Screen:** use-case labels: agent wallets / payment infrastructure / privileged agent tools / enterprise agents.

**Voice-over:**

"Any platform allowing an agent to move money or call privileged tools needs a control plane that can answer three questions: who authorized this, what exact action was allowed, and can an independent party verify what happened? Verigate is designed to provide that layer."

Do not imply hosted multi-tenant SaaS, KMS/HSM custody, or an independent security audit is already shipped.

## 2:48–3:00 — Close

**Screen:** source repository, judge commands, threat model, proof specification.

**Voice-over:**

"Do not take the model's word for it. Change the action. Verify the proof. See what gets blocked. Verigate — AI agents can act, but they cannot authorize themselves."

**Final on-screen links:**
- github.com/rudimentall1/verigate
- docs/DORAHACKS-JUDGE-PATH.md
- docs/threat-model.md
- docs/verigate-authority-proof-v1.md

## Recording checklist

- Record the terminal commands directly; keep their real output visible and readable.
- Use the current Anna Runtime screenshots or a fresh recording from the current App. Do not silently substitute mock UI for a live acceptance claim.
- Label the tamper demo as a local callback test, not a chain transaction.
- Label the Anna wallet prompt as cancelled; do not claim payment success.
- Keep the spoken problem statement in the first 10 seconds.
- The video is a demonstration, not a substitute for the public repo, test suite, threat model, and proof specification.
