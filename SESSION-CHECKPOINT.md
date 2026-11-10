# Verigate Arc Project Checkpoint

**Last updated:** 2026-11-10  
**Primary objective:** finish and evidence Verigate's Arc Mainnet Authority Registry integration for the Circle Developer Grants application (Questbook).  
**Scope:** Verigate + Arc only. Do not redirect this work to unrelated integrations.

## 1. Repository, branch and change boundaries

- Repository: `rudimentall1/verigate`
- Working branch: `integration/arc-authority`
- Branch HEAD at this checkpoint: `419b851df8bc8fc9df6ef83493d2d2fb1eb945df`
- Pull request: [#38 Integrate Arc on-chain authority registry](https://github.com/rudimentall1/verigate/pull/38)
- PR state: open, Draft, not merged.
- Do not merge, deploy, redeploy the Registry, close the PR, or modify the server without explicit user approval.

### GitHub branch versus current main

Compared on 2026-11-10:
- `main` HEAD: `8d689a6e0b20687152048e7c6b70c2fb780781c2`
- `integration/arc-authority` HEAD: `419b851df8bc8fc9df6ef83493d2d2fb1eb945df`
- Merge base: `be9b496d20496b794906b56388f170a0b7622c1b`
- Branch status: diverged; Arc branch is **26 commits ahead and 13 behind** current `main`.
- Do not describe the branch as based on the current main HEAD. PR body wording saying it is based directly on current main is stale.
- Reconcile the 13 incoming commits before proposing a merge. Do not merge as part of this task.

### Production server versus GitHub branch

Server comparison supplied by the user on 2026-11-10:
- Server path: `/opt/verigate`
- Server branch: `server-snapshot-20261110-083101`
- Server HEAD: `a63769cf1a730cb735b8f35a1d600ede36470c45`
- Server working tree was clean at inspection.
- Server has `SESSION_CHECKPOINT.md` (underscore), dated 2026-11-07. It is stale and describes the older investigation stage.
- GitHub branch has `SESSION-CHECKPOINT.md` (hyphen), this file.
- Merge base between server HEAD and GitHub branch HEAD: `5febe08f3be58d78aaabfbc7e60b54bc3ca55750`.
- `git rev-list --left-right --count HEAD...FETCH_HEAD` from the server returned `1 509`: one commit unique to the server history and 509 commits unique to the GitHub branch history after that merge base.
- Tree comparison reported 276 changed files, 35,612 insertions and 3,944 deletions. This is a broad repository-version divergence, not merely a checkpoint filename difference.
- These server-versus-GitHub numbers are a different comparison from the GitHub branch-versus-main numbers above. Never mix them.
- No server files, branches, services or deployments were changed during this comparison. The only server-side action was fetching the GitHub branch and running read-only Git inspection commands.
- Do not copy the GitHub branch wholesale to production. First review compatibility and deployment impact. Update the server checkpoint only after the user explicitly authorizes a server write.

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
- User explicitly confirmed that Verigate's Arc Authority Registry deployment was already completed. Treat deployment as done; do not ask the user to repeat deployment or redeploy it.
- This repository audit did not independently re-verify the deployment transaction or runtime bytecode on Arc Explorer. Preserve that distinction: user-confirmed deployment versus independently archived deployment evidence.

## 3. Implemented Arc architecture on `integration/arc-authority`

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
- Expiry is strict: `block.timestamp < validUntil`; authorization is invalid at the exact expiry timestamp.
- Registry stores an authorization ID, intent hash, executor, expiry and state; it does not store the complete payment payload.
- `integrations/arc_authority_registry.py` builds registration/consumption calldata and verifies transaction hash, chain ID, sender, destination, exact calldata, zero native value, successful receipt, block number/hash/timestamp, expected event and stored Registry state.
- Block lookup now converts the RPC hex block number into an integer before calling `get_block_by_number`.

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

## 4. Security boundary: supported and unsupported claims

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
- A Verigate-authorized live mainnet payment has been proven by the repository evidence reviewed here.

The Registry commits to the signed authorization through an intent hash. It does not itself execute or atomically gate the USDC transfer. The API/client sequence enforces the compliant application path; direct out-of-band wallet/RPC transfers remain outside that boundary.

## 5. Tests and current CI evidence

Relevant test files on `integration/arc-authority`:

- `tests/test_arc_api.py`: API status/authorization, exact transfer binding, generic-consume rejection, registration/consumption confirmation path.
- `tests/test_arc_authority_registry.py`: Registry deployment checks, calldata construction, transaction/receipt binding, event/state validation, block hash and trusted timestamp/expiry checks.
- `tests/test_arc_agent_enrollment.py`: operator enrollment, capability limits, replay/idempotency and revocation.
- `tests/test_agent_sdk_arc_api.py`: independent SDK enrollment and API flow.
- `tests/arc-client.test.mjs`: wallet chain/account validation, registration/consumption sequence, explicit payment broadcast and fail-closed cases.
- `tests/agent-sdk-arc-client.test.mjs`: Python SDK to JavaScript wallet client cross-language test.
- `scripts/compile_arc_authority.mjs`: compiles Registry and checks required ABI functions and strict expiry boundary.

### Latest verified CI

Workflow run [42802767752](https://github.com/rudimentall1/verigate/actions/runs/42802767752), for branch HEAD `419b851df8bc8fc9df6ef83493d2d2fb1eb945df`:

- Overall conclusion: **success**.
- `test` job: success. Full Python test suite, Python SDK ↔ JavaScript Arc client cross-language test, demo, and API smoke check all passed.
- `contracts` job: success. Arc wallet client workflow tests, atomic-state test, Arc Authority Registry compilation, and guard access-control test all passed.
- `anna-ui` job: success. Strict manifest validation, UI end-to-end test, and Linux binary build/smoke test all passed.
- All three jobs completed successfully. This supersedes the older CI evidence recorded in earlier versions of this checkpoint.
- CI proves the automated test/build paths on this commit. It does not prove a live Verigate-authorized Arc payment.

## 6. Audit findings and remaining work

### Required for Circle submission

1. Preserve the already-completed Registry deployment evidence: deployment transaction, contract address, deployer/owner, deployed bytecode identity and explorer links. Do not substitute the related Guardian demo transaction as Verigate evidence.
2. Capture one end-to-end Verigate Arc flow with separate transaction hashes for Registry registration and consumption. If no Verigate-authorized payment has occurred, state that plainly and do not fabricate one.
3. Prepare a concise architecture/evidence package for Circle: agent enrollment, signed authorization, Registry registration, Registry consumption, local nonce consumption, explicit payment handoff, and limitations.
4. Reconcile the branch's 13 commits behind current main before proposing a merge. Do not merge without explicit user approval.

### Code/security hardening to assess

- `_find_event` currently matches the first four bytes of event topic0 using a prefix check. Prefer comparing the full 32-byte Keccak event signature.
- Registry deployment verification checks non-empty bytecode and owner address, but does not pin/compare the deployed runtime bytecode hash to the reviewed source/build artifact. Add reproducible deployment metadata and code-hash evidence.
- Receipt verification compares the receipt block hash to the RPC's current canonical block hash, but no explicit multi-block finality wait policy is implemented. Decide and document the required Arc finality policy.
- Add an independent, non-mocked integration/evidence run for the deployed Registry and full registration/consumption flow when operationally safe. Keep payment broadcast separate and explicitly approved.
- If Registry consumption succeeds but local nonce consumption fails, the on-chain authorization is already irreversibly consumed and no payment is released. This is fail-closed; document the operational recovery path (issue a fresh authorization) and add a targeted test if not already covered.
- The latest Arc API test diff replaced older scenarios. Specifically review that tampered-authorization rejection and replay/failure behavior remain covered after the test refactor; the green CI alone does not prove coverage completeness.

### Adjacent API changes to keep separate from Arc claims

The same branch's `api/main.py` also adds wallet-enrollment governance and execution-submission ingestion/evidence routes. The submission route is documented in code as accepting an installation-signed SUBMITTED receipt. These are additional API surfaces, not proof of Arc functionality. Keep them out of the Circle Arc feature claims unless separately scoped and validated.

### Documentation correction completed

`docs/arc-mainnet-integration.md` describes the Registry-based flow and its actual security boundary. The older instructions to use generic `/v1/execution/consume` for Arc were incorrect; current code explicitly blocks that route for Arc authorizations.

## 7. Existing Arc evidence attribution

The repository's earlier Arc live-payment evidence relates to **Agentic Wallet Guardian v3**, a separate project by the same team. The documented transaction:

`0xd781e8b04b5ca89c3a34fcec50a6636049f7647d2b0e1b2bb64d5b1ee54daadf`

must not be attributed to Verigate. The Registry deployment is a separate user-confirmed deployment. A Verigate-authorized payment requires its own independently verifiable transaction evidence.

## 8. Next session startup rules

1. Read this file first.
2. Continue on `integration/arc-authority` and PR #38.
3. Keep the Circle Developer Grants / Questbook application as the business objective.
4. Do not reopen deployment or unrelated integrations as blockers.
5. Do not rerun work already evidenced here unless new code changes or a failed test make it necessary.
6. Before claiming a test passed, identify the exact commit and workflow run.
7. Do not assume this branch is current with main: the last recorded comparison is 26 ahead / 13 behind.
8. Do not sync this branch wholesale to the production server. The server snapshot is materially divergent.
9. No merge, redeploy or server modification without explicit approval.
