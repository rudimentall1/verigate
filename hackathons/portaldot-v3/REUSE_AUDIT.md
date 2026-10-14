# Verigate reuse audit for PortalDot V3

**Prepared:** 2026-10-13  
**Scope:** static source review of the public `main` branch for the PortalDot Hacker House.  
**Verification boundary:** repository files and source structure were inspected. The full test suite was not run in this review, the remote development machines were offline, and live PortalDot RPC connectivity was not tested. Nothing in this document claims a PortalDot deployment exists.

## Decision

Keep Verigate as the existing authority control plane. Build the PortalDot submission as a separate repository, tentatively `rudimentall1/verigate-portaldot`, with a small integration bridge, a narrowly scoped Solidity contract, tests, deployment scripts and demo evidence.

Do not copy the Verigate core, API, SQLite store, router, signing code or the whole test suite into the new project. Integrate against a running local Verigate instance or a documented checkout/path. Keep the adapter's chain-specific behavior in the new repository. This is the quickest route that preserves one source of truth and a transparent hackathon change history.

## Repository map reviewed

The current recursive Git tree contains 284 entries, including directories, source files, tests, docs, screenshots and large demo media. Relevant paths:

| Existing path | What it provides | How the PortalDot project should use it |
|---|---|---|
| `core/models.py` | `ActionIntent`, decision models and canonical action/context representation | Reference the intent fields and exact action semantics; do not copy the module |
| `core/engine.py`, `core/authorization.py` | Policy evaluation and authority issuance orchestration | Keep as the decision source through Verigate's existing interface |
| `core/identity.py`, `core/capabilities.py` | Agent-signed intents, identity binding, scoped and revocable capabilities | Use the signed-intent path in the scenario; do not invent a parallel authority registry |
| `core/policy.py`, `policies/default.yaml` | Deterministic policy and target/network/limit controls | Define an explicit policy for the demo and test ALLOW/BLOCK |
| `attest/receipt.py`, `attest/verify.py` | Ed25519-signed decision receipts and separate execution authorizations | Verify the off-chain authorization with the existing protocol; Solidity cannot natively validate this Ed25519 artifact |
| `api/main.py`, `api/schemas.py` | HTTP API including `POST /v1/actions/authorize` | Best integration seam if running Verigate as a separate process; document authentication and test the actual request/response contract |
| `enforcement/evm.py`, `enforcement/evm_rpc.py` | Existing EVM authorization gate and dependency-light JSON-RPC client | Treat as reference/reusable runtime capability only after checking the import/deployment boundary; don't blindly vendor it |
| `enforcement/chain_verification.py` | Independent EVM transaction-receipt observation | Reuse the evidence pattern for a transaction receipt and independently queried chain ID |
| `enforcement/networks.py` | EVM/Solana network registry; PortalDot V3 is not a named default entry | Do not modify core just to add one hackathon network; use a local descriptor/adapter in the new repository |
| `contracts/VerigateAtomicStateGuard.sol` | Executor-restricted atomic external-state guard | Do not treat it as an on-chain per-action authorization contract; see security note below |
| `tests/test_evm_enforcement.py`, `tests/test_evm_rpc.py`, `tests/test_chain_verification.py`, `tests/test_tamper_enforcement.py`, `tests/test_authorization_service.py`, `tests/test_api_universal_action.py` | Existing regressions for EVM artifacts, authorization, replay/tampering and chain evidence | Read these as reference; new repo must add its own PortalDot-specific tests |
| `docs/threat-model.md`, `docs/security-configuration.md`, `AGENTS.md` | Explicit trust boundaries, production configuration, engineering invariants | Preserve the documented limitations and security language in the new README |
| `scripts/test_guard_access_control.mjs`, `scripts/e2e_atomic_state.mjs` | Local Solidity/Ganache checks for current guard behavior | Useful examples of local tests; do not treat a local Ganache run as PortalDot evidence |
| `hackathons/portaldot-v3/PLAN.md` | Current network notes and planned integration boundary | Keep the audit and planning links here; implementation remains in the new repo |

## Current stack and commands

Verigate's root runtime uses Python with FastAPI/Pydantic/Uvicorn, PyYAML, cryptography and SQLite. The root has `requirements.txt` but no root `pyproject.toml`; the separately published standalone verifier has its own packaging under `packaging/verigate-verify/`. Do not assume the whole root is installable as `pip install verigate`.

Existing Python test command:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

Existing contract-tooling commands (from the Verigate repository root, with npm dependencies installed):

```bash
npm run test:guard
npm run test:atomic
```

This review did not execute these commands. The new PortalDot repository should own and run its own tests; run relevant Verigate regression tests separately if core code is touched.

The existing `package.json` uses ethers v6, Ganache and solc; the current official PortalDot V3 guide demonstrates Hardhat with Solidity 0.8.24. A new repo should begin with the guide's conservative compiler target and lock its dependencies. Do not copy the entire root package lock without a reason.

## Security findings that directly affect this integration

### 1. The current guard is not a per-action authorization verifier

The current `VerigateAtomicStateGuard` has already been hardened against the historical permissionless relay: it stores an immutable non-zero `executor`, allows only that executor to call `execute`, and requires `value == msg.value`. The local guard tests cover non-executor callers, lying/honest oracles, stale/fresh state and value behavior.

However, the contract still does **not** verify a separate signed authorization for each target/value/calldata action. Its own source and `docs/threat-model.md` state that the on-chain call trusts the off-chain router and executor key. Historical deployments made before the access-control fix must not be reused.

**Decision:** do not copy this contract unchanged and market it as full on-chain Verigate enforcement. For the PortalDot demo, prefer one narrow action contract whose execution is authorized by an EIP-712 signature bound to chain ID and verifying contract, exact recipient/amount/action, unique nonce and deadline. Avoid a generic caller-selected `target.call` relay.

### 2. Ed25519-to-EVM boundary must be explicit

Verigate signs its decision receipt and execution authorization with Ed25519. An ordinary Solidity EVM contract does not automatically verify those signatures. If the demo creates an EIP-712 authorization after verifying the Verigate authorization off-chain, the EIP-712 signer/bridge becomes an explicit trust boundary. It must verify the original signature, ALLOW decision, expiry, nonce, exact intent/action fields and target policy before signing. Do not describe the resulting EIP-712 signature as the original Verigate signature.

### 3. Keep the first MVP narrower than the existing architecture

For time-to-demo, implement a single useful operation and no oracle/general executor. Suggested scenario: a Verigate-approved transfer from a demo treasury to a recipient, with a fixed test token configured at deployment. The PortalDot transaction is paid in `tPOTv3` gas. The contract should check the EIP-712 signer, chain/domain, recipient, amount, deadline and replay nonce. Unauthorized/blocked actions must never receive a valid bridge signature; the demo should show that no transaction was broadcast for a blocked request.

### 4. Network and wallet evidence are prerequisites

Current official testnet guide:
- EVM RPC: `https://testnetv3-eth-rpc.feso-apps.xyz`
- Substrate RPC: `wss://testnetv3-node.feso-apps.xyz`
- Chain ID: `420420777`
- Native test token: `tPOTv3`, 14 decimals as documented by the testnet guide
- Node explorer: `https://node-console.feso-apps.xyz/`
- Guide: `https://github.com/ItsCogumellum/portaldot-v3-testnet-guide`

The guide explicitly warns that an EVM H160 account and its mapped Substrate SS58/AccountId32 address must not be assumed identical. Use Node Explorer → Developer → Runtime calls → `reviveApi.accountId` to resolve the mapping before requesting or sending test POT. Live RPC connectivity remains unverified by this source review.

## Proposed integration boundary

1. A Verigate process evaluates the exact action using an agent-signed intent, identity, capability and deterministic policy.
2. A small bridge verifies the returned Ed25519 ExecutionAuthorization using Verigate's trusted public key and checks all required fields against the operation it is about to authorize.
3. Only after this verification does the bridge produce an EIP-712 signature for the dedicated PortalDot contract. The bridge key is kept in a local `.env` or other secret store and never committed.
4. The contract verifies the EIP-712 domain and exact action fields, enforces expiry and one-time nonce consumption, and performs only the narrow configured action.
5. A separate RPC read checks `eth_chainId`, transaction receipt and resulting state. Evidence records the commit, contract address and transaction hashes only after they are verified.

If the bridge cannot be implemented safely in the available time, reduce scope and describe the actual trust boundary. Do not fake a chain-enforced authorization demo with a UI-only ALLOW/BLOCK result.

## What to carry into the new repository

**Reuse as behavior and protocol references:** `ActionIntent` fields, Verigate identity/capability/policy flow, Ed25519 authorization verification, one-time nonce semantics, RPC receipt observation, tamper/replay test patterns and threat-model language.

**Build fresh in `verigate-portaldot`:** PortalDot network preflight, Hardhat setup, narrow Solidity contract, EIP-712 bridge adapter, deployment script, end-to-end tests, demo CLI/UI, architecture diagram and evidence folder.

**Do not copy:** `core/`, `api/`, `attest/`, `enforcement/router.py`, the whole Verigate test suite, Anna/Executa assets, old deployment addresses, credentials, or claims that the off-chain system runs on-chain.

## Audit status

- [x] Recursive source tree inventoried.
- [x] Core models, policy, identity/capability authorization, EVM adapter/RPC and router boundary inspected.
- [x] Existing guard contract, threat model, changelog and access-control tests inspected.
- [x] Official V3 guide and current testnet parameters checked.
- [ ] Full automated Verigate suite run.
- [ ] PortalDot JSON-RPC preflight run against the live endpoint.
- [ ] New repository created.
- [ ] New integration implemented, tested or deployed.

The unchecked items must stay unchecked until directly verified.


## Implementation kickoff update (2026-10-14)

The separate public repository has now been created: [rudimentall1/verigate-portaldot](https://github.com/rudimentall1/verigate-portaldot).

The initial contract and project scaffold were committed in commit 090c8ee. The Verigate bridge-signing CLI and binding tests were added in commit 6c59a74. GitHub Actions completed successfully on the latter commit: 15 tests passed and Solidity 0.8.24 compilation succeeded.

This confirms the code was pushed and that hosted CI passed. It does not confirm a developer-local run, a live PortalDot RPC response, a real authorization response through the bridge, a wallet mapping, or an on-chain deployment. No deployment evidence has been recorded.
