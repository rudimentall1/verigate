# Verigate Arc Project Checkpoint

**Last updated:** 2026-11-10  
**Primary objective:** finish and evidence Verigate's Arc Mainnet Authority Registry integration for the Circle Developer Grants application (Questbook).  
**Scope:** Arc only. Do not redirect this work to Anna or unrelated integrations.

## 1. Repository and change boundary

- Repository: `rudimentall1/verigate`
- Working branch: `integration/arc-authority`
- Pull request: [#38 Integrate Arc on-chain authority registry](https://github.com/rudimentall1/verigate/pull/38)
- PR state at audit: Draft, not merged.
- Do not merge, deploy, redeploy the Registry, close PRs, or modify the server without explicit user approval.
- The Arc branch is not synchronized with `main`. GitHub compare after checkpoint/doc commits reported **24 commits ahead, 7 behind**, merge base `be9b496d20496b794906b56388f170a0b7622c1b`; `main` was `1b2a79ac6aa79aa0e717d240338d63a666f0f940`. Reconcile the seven incoming commits before merge. Do not assume the branch is current with main.

## 2. Arc network and deployed Registry configuration

- Network: Arc Mainnet
- Chain ID: `5042` / `0x13b2`
- RPC: `https://rpc.mainnet.arc.io`
- Explorer: `https://explorer.arc.io`
- Canonical Arc USDC ERC-20: `0x3600000000000000000000000000000000000000`
- ERC-20 transfer precision: 6 decimals
- Native Arc gas asset: USDC with 18-decimal native-value denomination
- Registry address configured in code: `0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D`
- Registry executor configured in code: `0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C`
- User has explicitly confirmed that the Verigate Arc Authority Registry deployment was already completed. Treat deployment as done; do not ask the user to repeat deployment or re-deploy it.
- The registry client checks Arc chain ID, deployed bytecode and `owner()` against the configured executor at runtime. This audit did not initiate a new live deployment check or transaction.

## 3. Implemented architecture

### Agent identity and enrollment

- `integrations/agent_sdk.py` creates/loads agent Ed25519 keys locally; key files are created with owner-only permissions and unsafe existing permissions are rejected.
- SDK builds a public-only enrollment package with agent ID, public key, capability ID, recipient allowlist, per-action USDC limit and expiry.
- `scripts/enroll_agent_arc.py` performs operator-controlled enrollment into Verigate storage. There is no public self-registration endpoint.
- Agent SDK signs the exact Arc payment ActionIntent, including sender, recipient, amount and canonical ERC-20 transfer calldata.

### Arc payment authorization

- `integrations/arc.py` defines Arc network/token constants, 6-decimal ERC-20 amount encoding, exact transfer calldata and strict transaction-envelope validation.
- `GET /v1/integrations/arc/status` checks live RPC chain ID, block/gas metadata, canonical USDC bytecode and token decimals.
- `POST /v1/integrations/arc/authorize` validates Arc payment type/network/asset, canonical token metadata, sender/recipient/amount/calldata, agent signature, identity, capability and policy.
- When executable authority is issued, API verifies Registry configuration and returns the registration transaction. It deliberately returns `wallet_transaction: null` at this stage.

### On-chain authority registry

- Contract: `contracts/arc-authority/src/VerigateAuthorityRegistry.sol`
- Registration is issuer-gated.
- Consumption is executor-gated and checks exact authorization ID, intent hash, expiry, revocation and one-time state.
- Revocation is supported for owner/issuer.
- Registry stores an authorization ID, intent hash, executor, expiry and state; it does not store the complete payment payload.
- `integrations/arc_authority_registry.py` builds registration/consumption calldata and verifies transaction hash, chain ID, sender, destination, exact calldata, zero native value, successful receipt, block number/hash/timestamp, expected event and stored Registry state.
- The block timestamp is checked against authorization issuance and expiry. The expiry boundary is strict: inclusion at or after `expires_at` is rejected.

### API confirmation and execution boundary

1. Agent submits signed request to `/v1/integrations/arc/authorize`.
2. Wallet signs/broadcasts Registry registration.
3. `/v1/integrations/arc/registration/confirm` verifies registration and returns consume transaction.
4. Wallet signs/broadcasts Registry consumption.
5. `/v1/integrations/arc/consume/confirm` verifies consumption, then calls the Verigate ExecutionRouter with the verified Arc block timestamp.
6. Router consumes the local one-time nonce. Only after success does API return the exact wallet payment transaction and Arc authority evidence.
7. Generic `POST /v1/execution/consume` explicitly rejects Arc authorizations with HTTP 409 to prevent bypassing the Registry flow.

### Wallet client

- `integrations/arc-client.mjs` is an EIP-1193 orchestration helper.
- It checks Arc chain ID and the required account before wallet signing.
- It submits and waits for registration and consumption receipts, calls the confirmation endpoints, and returns the payment transaction only after `execute === true`.
- It does **not** broadcast the payment automatically.
- `broadcastAuthorizedArcPayment` is a separate explicit wallet operation.

## 4. Security boundary: claims that are and are not supported

**Supported by this implementation:**
- Exact signed intent and canonical USDC transaction envelope are bound before authority issuance.
- Identity, capability and policy are checked before authority is issued.
- Registration and consumption are independently confirmed against Arc RPC and Registry state.
- Registry consumption is one-time and executor-bound.
- Local Verigate execution nonce is consumed only after confirmed on-chain Registry consumption.
- The payment transaction is handed back separately for explicit wallet approval; Verigate does not custody wallet keys or USDC.

**Do not claim:**
- The Registry is an escrow contract or an on-chain USDC transfer guard.
- This version makes it technically impossible for a wallet owner or external caller to submit a direct USDC transfer outside the Verigate client flow.
- A Verigate-authorized live mainnet payment has been proven by the repository evidence currently reviewed.

The Registry commits to the signed authorization through an intent hash. It does not itself execute or atomically gate the USDC transfer. The API/client sequence enforces the compliant application path; direct out-of-band wallet/RPC transfers remain outside that boundary.

## 5. Test inventory and evidence

Relevant test files present on `integration/arc-authority`:

- `tests/test_arc_api.py`: API status/authorization, exact transfer binding, generic-consume rejection, registration/consumption confirmation path.
- `tests/test_arc_authority_registry.py`: Registry deployment checks, calldata construction, transaction/receipt binding, event/state validation, block hash and trusted timestamp/expiry checks.
- `tests/test_arc_agent_enrollment.py`: operator enrollment, capability limits, replay/idempotency and revocation.
- `tests/test_agent_sdk_arc_api.py`: independent SDK enrollment and API flow.
- `tests/arc-client.test.mjs`: wallet chain/account validation, registration/consumption sequence, explicit payment broadcast and fail-closed cases.
- `tests/agent-sdk-arc-client.test.mjs`: Python SDK to JavaScript wallet client cross-language test.
- `scripts/compile_arc_authority.mjs`: compiles Registry and checks required ABI functions and strict expiry boundary.

### Last confirmed CI evidence

Workflow run [42789221106](https://github.com/rudimentall1/verigate/actions/runs/42789221106), commit `19219d76025f8e25363d79b25b543162316577c4`:

- Python test job: **608 tests passed**.
- Arc Authority Registry Solidity compile: **PASS**.
- The run's contract job also attempted unrelated Ganache atomic/guard scripts; those failed because the optional native module `uws_linux_x64_127.node` was unavailable.
- This run predates the current Arc-specific CI steps now present in `.github/workflows/ci.yml`. Therefore it does **not** prove that `npm run test:arc-client` or `node --test tests/agent-sdk-arc-client.test.mjs` passed in CI.
- Current branch CI configuration includes both Arc client test commands. A new run on the current branch revision is still needed to establish their CI result.

All listed API/Registry/SDK tests use mocks or deterministic RPC fixtures for chain and wallet interactions. They establish tested software behavior, not a live Verigate-authorized mainnet payment.

## 6. Audit findings and remaining work

### Required before Circle submission

1. Run current-branch CI and capture results for both Arc client tests and Registry compilation.
2. Preserve the already-completed Registry deployment evidence: deployment transaction, contract address, deployer/owner, deployed bytecode identity and explorer links. Do not substitute the related Guardian demo transaction as Verigate evidence.
3. Capture one end-to-end Verigate Arc flow with separate transaction hashes for Registry registration and consumption. If no Verigate-authorized payment has occurred, state that plainly and do not fabricate one.
4. Prepare a concise architecture/evidence package for Circle: agent enrollment, signed authorization, Registry registration, Registry consumption, local nonce consumption, explicit payment handoff, and limitations.
5. Reconcile the branch's five commits behind main before proposing a merge.

### Code/security hardening to assess

- `_find_event` currently matches the first four bytes of event topic0 using a prefix check. Prefer comparing the full 32-byte Keccak event signature to avoid relying on a 4-byte prefix.
- Registry deployment verification checks non-empty bytecode and owner address, but does not pin/compare the deployed runtime bytecode hash to the reviewed source/build artifact. Add reproducible deployment metadata and code-hash evidence.
- Receipt verification compares the receipt block hash to the RPC's current canonical block hash, but no explicit multi-block finality wait policy is implemented. Decide and document the required Arc finality policy.
- Add an independent, non-mocked integration/evidence run for the deployed Registry and full registration/consumption flow when operationally safe. Keep payment broadcast separate and explicitly approved.
- If Registry consumption succeeds but local nonce consumption fails, the on-chain authorization is already irreversibly consumed and no payment is released. This is fail-closed; document the operational recovery path (issue a fresh authorization) and add a targeted test if not already covered.

### Documentation correction completed in this branch

`docs/arc-mainnet-integration.md` was updated to describe the Registry-based flow and its actual security boundary. The old document incorrectly instructed users to call generic `/v1/execution/consume` for Arc, which current code explicitly blocks.

## 7. Existing Arc evidence attribution

The repository's earlier Arc live-payment evidence relates to **Agentic Wallet Guardian v3**, a separate project by the same team. The documented transaction:

`0xd781e8b04b5ca89c3a34fcec50a6636049f7647d2b0e1b2bb64d5b1ee54daadf`

must not be attributed to Verigate. The Registry deployment is a separate user-confirmed deployment. A Verigate-authorized payment requires its own independently verifiable transaction evidence.

## 8. Next session startup rules

1. Read this file first.
2. Continue on `integration/arc-authority` and PR #38.
3. Keep the Circle Developer Grants / Questbook application as the business objective.
4. Do not reopen deployment, Anna, or unrelated integrations as blockers.
5. Do not re-run work already evidenced here unless new code changes or a failed test make it necessary.
6. Before claiming a test passed, identify the exact commit and workflow run.
7. No merge, redeploy or server modification without explicit approval.
