# Verigate Authority — 90-second judge route

This is the shortest reproducible way to evaluate the product's core claim without trusting the LLM, a screenshot, or a blockchain explorer.

## Opening statement

> AI agents can propose actions. They cannot authorize themselves. Verigate makes authorization deterministic, binds it to the exact action, enforces it before execution, and exports proof that can be checked offline.

## 0:00–0:25 — Show the authority lifecycle and proof

From the repository root, run:

    python examples/genesis_demo.py

Expected evidence:
- Genesis 2.0 lifecycle contract passes.
- The independent verifier validates the original proof and prints RESULT: VALID.
- The demo changes the proof package and requires RESULT: INVALID.
- The command ends with GENESIS 2.0 DEMO: PASS.

This is a local protocol demonstration. It is not a claim that a mainnet transaction was sent.

## 0:25–0:45 — Attack the approved action

Run:

    python demo_tamper_enforcement.py

Expected evidence:
- Change the tool endpoint after ALLOW: VERIGATE: BLOCK, Broadcasts: 0.
- Change the EVM transaction destination after ALLOW: VERIGATE: BLOCK, Broadcasts: 0.
- The unchanged authorization is accepted by a local demo callback.

Important: the script uses an in-process callback that returns demo-tx-hash. It does not contact a blockchain or broadcast a real payment. The two zero-callback results are the security proof.

## 0:45–1:30 — Show the user-facing Anna integration

Use the Anna Runtime captures and acceptance record:
- https://github.com/rudimentall1/verigate/blob/main/anna/README.md
- https://github.com/rudimentall1/verigate/blob/main/docs/ANNA-RELEASE-GATE.md

Show this sequence:
1. User enters a payment in plain language.
2. Anna host LLM interprets it and returns an advisory contextual review.
3. Verigate's deterministic engine returns ALLOW, WARN, or BLOCK.
4. The App verifies the signed Decision Receipt.
5. A separate user confirmation is required for a one-time Execution Authorization.
6. ExecutionRouter consumes the permission before wallet hand-off.

Be explicit about the test boundary: the live 25 USDC Base test reached the MetaMask prompt, then the user cancelled because the test wallet was empty. No wallet signature, broadcast, transaction hash, or on-chain settlement occurred.

## What to ask judges to inspect

- core/authorization.py and enforcement/router.py: exact-action binding and one-time authorization enforcement.
- tools/verigate_proof_verifier.py: independent proof verification.
- docs/verigate-authority-proof-v1.md: portable proof validity contract.
- docs/threat-model.md: threats and trust boundaries.
- tests/: adversarial and lifecycle regression coverage.

## Mapping to common DoraHacks judging dimensions

- **Innovation:** authority is separated from the LLM; the model cannot authorize itself.
- **Technical depth:** signed identities/capabilities/policies, one-time exact-action permissions, router enforcement, offline proof verification.
- **Impact:** the control layer is relevant to agentic payments and privileged tools, not only one conversational UI.
- **Code quality:** the two demos are runnable; tests and CI are public; the proof verifier is separate from the runtime.
- **Business feasibility:** SDK/verifier and integration-led B2B entry point exist; a hosted multi-tenant enterprise service is still roadmap.

The hackathon's own track requirements and prize rubric take precedence over these common dimensions.
