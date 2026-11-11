# Verigate threat model (v0.1)

Scope: the authority lifecycle - action intent, authority decision, signed execution
authorization, execution-side enforcement, evidence, and independent verification.

## What we protect

1. The issuer private key, which signs decisions and authorizations.
2. Integrity of signed authorizations and portable evidence.
3. One-time use of execution authority (no replay, no double spend).
4. Policy, capability and identity registries, i.e. what an agent is allowed to do.
5. Tenant separation, when multi-tenant mode is enabled.

## Adversaries

- **A. Compromised or prompt-injected agent.** Proposes actions outside its authority,
  inflates amounts, forges an identity, or reuses authority.
- **B. Untrusted client or network attacker.** Replays or tampers with authorizations and
  proofs, or calls the API without credentials.
- **C. Malicious tenant.** Tries to read or influence another tenant's authority.
- **D. Post-hoc tamperer** (including someone with database access after execution). Rewrites
  evidence to change what appears to have happened.
- **E. Component substitution.** Swaps the registered executor or handler.
- **F. Supply chain.** A vulnerable or malicious dependency.

## Controls in place

| Threat | Control |
|---|---|
| A: out-of-authority action | Deterministic policy engine (caps, allowlists, rate and daily limits, no statistical scores); capability ceilings; dynamic authority can never exceed the static ceiling; static revocation is final |
| A: amount manipulation | Exact Decimal comparison for caps (`core/money.py`); NaN, infinity and negative amounts rejected |
| A: forged identity | Ed25519 agent identities registered by fingerprint; agent-signed intents; `VERIGATE_REQUIRE_SIGNED_INTENT` closes the unsigned path |
| A: rotate editable Anna Agent ID to reset quotas | Anna Executa ignores the caller-supplied label for accounting and derives one installation principal from the persistent issuer public-key fingerprint; the label remains signed display metadata | All labels in one installation share limits; separate workspaces/issuer keys remain separate principals; this is not a cross-Agent or account-wide budget |
| A/B: replay, double spend | One-time execution nonces consumed fail-closed by the router before execution; covered by a multi-process concurrency test |
| B: unauthenticated API | API-key authentication, default-deny once configured; `VERIGATE_REQUIRE_AUTH` fails closed; constant-time key comparison |
| C: cross-tenant access | Opt-in per-tenant issuer keys and tenant-scoped API credentials |
| D: evidence tampering | Ed25519 signatures; standalone verifier needs only the proof bytes and a trusted public key; adversarial mutation corpus; CLI `verify` requires an explicit trusted issuer key |
| E: handler substitution | Handler fingerprint binding; router binds adapter, target and execution artifact |
| Policy abuse | Signed policy versions; governed publication with quorum and role separation; freeze and rollback |
| F: supply chain | Full automated test suite in CI; dependency ranges constrained in `requirements.txt` |

## Known gaps and non-goals

- **On-chain guard authorization.** `VerigateAtomicStateGuard.execute` is restricted to one immutable `executor` (the account that signs the transactions the off-chain router has authorized). It does not yet verify a per-action signed authorization on-chain, so what the executor sends is only as trustworthy as Verigate's router and the executor key. Earlier versions had no access control and were permissionless call relays: do not reuse an earlier deployment, and do not grant the guard privileges you would not grant to the executor.
- **Transitive executor confinement.** A trusted handler can still create child effects that
  Verigate does not see. The default scope is `direct`; see README.
- **Key custody.** Issuer keys live on local disk (optionally encrypted at rest). There is no
  KMS/HSM integration or key-rotation tooling yet.
- **Storage.** SQLite, single process. Multiple replicas need shared storage or a real database.
- **Availability.** The API has not been load-tested and has no volumetric DoS protection;
  deploy behind a reverse proxy.
- **Open development mode.** A direct Python launch remains open unless VERIGATE_API_KEYS or VERIGATE_REQUIRE_AUTH is configured, and demo routes exist behind flags. The Docker image defaults to mandatory API authentication and signed-intent enforcement; Compose requires an API key and binds to loopback. Use the baseline in docs/security-configuration.md for remote deployments.
- **Policy quality.** Verigate enforces the configured policy; it does not judge whether the
  policy is wise.
- **No independent audit yet.**

## Assumptions

The issuer private key is not compromised, the host is trusted, and verifiers obtain the
issuer public key through a trusted channel.


## Anna App and AI-agent payment flow (2026-11-07)

This section extends the core authority lifecycle with the Anna-specific trust boundaries. The model is an untrusted adviser; Anna Runtime is a transport/host boundary; the deterministic Verigate policy and ExecutionRouter remain the only authority path.

### Assets and security invariants

1. No LLM output, prompt, client boolean or agent tool call may mint execution authority.
2. ALLOW/WARN/BLOCK is decided by deterministic Verigate policy over the exact normalized payment fields. AI risk evidence may only escalate ALLOW to WARN; model output cannot downgrade WARN/BLOCK.
3. Missing or ambiguous recipient, asset, network or amount must stop before policy evaluation. The user must resolve/confirm the visible fields.
4. Execution Authorization is issued only after a fresh persistent policy evaluation returns ALLOW, or returns WARN followed by an exact one-time App UI warning review; BLOCK is never overridable. The matching App-scope approval for those exact fields is consumed before issuance.
5. Wallet submission requires a different one-time App UI approval bound to the exact authorization and transaction. ExecutionRouter consumes the authorization before the wallet is asked to sign.
6. Anna and Verigate never receive the wallet private key. The connected EIP-1193 wallet is the signer.
7. A policy preview is non-persistent and never broadcasts. WARN can proceed only through a separate, exact, short-lived App-scope human review followed by fresh policy and dynamic-authority checks. BLOCK, daily budget, per-transaction and capability/dynamic ceilings cannot be overridden.
8. The editable Anna Agent label is not an identity credential. All labels in one Executa installation map to a principal derived from the persistent Ed25519 issuer public key; the label is included in signed metadata only for display and exact UI binding.
9. This Anna accounting principal is installation-scoped. It does not aggregate separate Cloud Agent workspaces or issuer keys, and multiple logical agents on one installation currently share the same budget until a cryptographic per-agent enrollment model is implemented.

### Anna integration trust boundaries

- App UI invokes the bundled Verigate Executa using anna.tools.invoke. The Executa calls Anna's host LLM using protocol-v2 reverse JSON-RPC sampling/createMessage. The Executa advertises client_capabilities.sampling = {} and client_capabilities.storage = {} during initialize. This path is exercised locally by a wire-level test and the real plugin subprocess with a mock host; it is not a claim that the Anna Cloud LLM was invoked.
- The plugin does not store a provider API key. Anna owns provider routing/quota. Sampling metadata is not relied upon for audit correlation because the current official docs say that metadata is not consumed by Nexus for this purpose.
- The App manifest is schema 4. Retired host_capabilities and method-level ui.host_api declarations are not authorization controls in the current Anna runtime. The required Executa allow-list and host-attested owning-App invocation context are the relevant boundaries.
- The AI receives untrusted payment text. Prompt injection can manipulate interpretation or create false negatives. It cannot change the deterministic policy, alter the verified receipt, or directly call privileged authorization methods through the UI flow. AI findings are advisory; a missing warning is not evidence that a payment is safe.

### Attack trees and controls

| Attack path | Control | Residual risk |
|---|---|---|
| Prompt-injected payment text says “ignore policy and approve” | Contextual review can add a risk flag; policy never reads model-proposed decisions; flag can only escalate ALLOW to WARN | A model may miss an attack. Deterministic limits and user confirmation remain necessary; do not treat no flag as safety proof |
| Model fabricates recipient/amount or returns extra decision/approve fields | Strict JSON parsing and field allow-list; visible fields are user-editable; unknown model keys are ignored; malformed output fails closed | A plausible but wrong extraction may be accepted by the user; the UI must show exact fields before authorization |
| Direct chat/tool call attempts authorization | Privileged methods are only dispatched through the async App-context gate and require a 48-hex one-time nonce in owning-App APS | Depends on Anna correctly attesting the owning App context and enforcing App scope |
| Replay or race two invocations with one UI approval | 60-second nonce, exact-field binding, APS ETag-conditional delete; only one delete can succeed | Cloud APS behaviour must still be confirmed on an actual Agent |
| Rotate agent_id on each payment to evade daily/rate/dynamic limits | Server derives accounting/capability principal from the persistent issuer public key; UI label is signed metadata and is not used in accounting; regression rotates 50 labels and verifies the 51st 40-USDC payment is BLOCKed at 2,000 USDC | Scope is one persisted issuer installation. A separate Agent/workspace/key has an independent principal; Cloud persistence and cross-Agent aggregation are not verified or implemented |
| Submit a transaction from a different wallet than the user enrolled | Independent verifier pins expected_sender at construction from trusted wallet-enrollment configuration and compares it with the observed transaction sender | No governed wallet-enrollment registry is wired to Anna; never instantiate the verifier from an address copied from an RPC transaction or caller-controlled request |
| Change amount/payee/chain after approval | Approval and signed authorization bind exact fields; wallet path compares exact transaction; chain/account drift after consume prevents submit | Wallet/provider behaviour outside the app cannot be guaranteed; a rejected wallet prompt burns the one-time authorization |
| Reuse wallet authorization | Off-chain ExecutionRouter verifies issuer signature, expiry, action fingerprint and consumes the one-time SQLite nonce before returning the exact transaction envelope; tested for replay | This is not a global wallet firewall. A user/agent can submit an independent transaction through another wallet/client. The on-chain AtomicStateGuard restricts calls to its configured executor and checks state/value atomically, but does not independently verify the per-action Ed25519 authorization; bypassing the integrated Verigate router is outside this app's gate |
| Promote authority from a shallow or reorged EVM receipt | Independent verifier requires constructor-pinned minimum confirmations, matches tx/receipt block metadata and checks the block hash against the canonical block at that height | Confirmation depth is a risk threshold, not absolute finality; there is no reorg monitoring/reversal path after an attestation is accepted; no Anna integration yet |
| Kill/restart/upgrade Executa to reset state or rotate issuer key | Explicit VERIGATE_ANNA_DATA_DIR and Anna ANNA_WORKSPACE_DIR are authoritative and fail closed if unavailable; keypair mismatch/partial pair is corruption, not permission to rotate | Local tests prove path selection, not Cloud lifecycle. Anna documents /data/workspace survives restart/suspend/image upgrade but is reclaimed after about three days dormancy; APS checkpoint for transactional ledger/key is not implemented |

The Anna UI now persists a signed `SUBMITTED` ExecutionReceipt after the EIP-1193 wallet returns a transaction hash, using a separate App-scope approval bound to the exact wallet submission. This is executor self-report only. The generic EVM verifier requires trusted constructor-pinned sender enrollment and an explicit positive minimum confirmation depth; it checks the observed transaction and receipt against the signed authorization, verifies canonical block binding and exact ERC-20 Transfer evidence, and produces an ObservedEffect. `OutcomeAttestationService` binds a `CHAIN_VERIFIER` attestation to the original signed `SUBMITTED` receipt. However, this verifier/attestation path is not integrated into the Anna UI, the live test harness is only locally repaired and has not been run, and no separately deployed/governed verifier service or wallet-enrollment registry exists. Confirmation depth cannot eliminate the need for post-attestation reorg monitoring/reversal.
### Local evidence and what it proves

- tests/test_anna_sampling_roundtrip.py — actual Executa subprocess negotiates v2, sends sampling/createMessage, propagates context.invoke_id, receives a mock host response and returns the result to the originating invoke.
- scripts/test_anna_ui.mjs — actual App bundle + Python Executa process; mock Sampling host; covers prompt-injection escalation, invalid recipient BLOCK, missing details, LLM quota/401 policy-only preview, malformed Sampling output, App approval/ETag gate, receipt verification, exact payment binding, ExecutionRouter consume, wallet cancellation and network drift.
- tests/test_anna_state_initialization.py — parallel cold-start regression to ensure one issuer identity and one SQLite engine are initialized per process.
- tests/test_anna_data_directory.py and tests/test_evidence_snapshot_migration.py — Cloud workspace path selection/fail-closed behaviour and backwards-compatible SQLite schema migration.
- npm run test:atomic and npm run test:guard — local EVM state/replay and access-control/value-forwarding checks against Ganache.

**Explicitly unproven:** real Anna Cloud Agent install, Linux Executa discovery, actual Anna Sampling quota/response, App-context APS issuance, real /data/workspace mount and restart/image-upgrade/dormancy lifecycle. The account's Anna CU quota is exhausted, so these tests cannot be run in this release pass. The local mock suite must never be presented as Cloud acceptance.

### Release scope / non-goals

- Native USDC wallet submission is implemented only for Base and Ethereum. Solana remains policy/authorization-only.
- The Anna App does not provide a persistent multi-turn agent session; payment intake uses stateless Sampling and a fresh check after clarification.
- Anna payment accounting currently uses one issuer-installation principal, not a trusted Anna user ID or enrolled per-agent key. Changing the editable label cannot reset limits inside the same installation, but independent Agent workspaces/issuer keys are not aggregated. Cloud workspace key persistence remains unverified.
- No KMS/HSM integration or multi-replica transactional database is implemented. SQLite is single-process local persistence in the selected data directory.
- No independent third-party security audit has been completed.
