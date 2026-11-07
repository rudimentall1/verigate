# Verigate Arc — Session Checkpoint

**Last updated:** 2026-11-07  
**Status:** investigation complete; implementation NOT complete  
**Canonical project:** `rudimentall1/verigate`  
**Working branch:** `feat/evm-wallet-identity-arc`  
**Checkpoint rule:** read this file before doing any work in a new session. Then inspect the live repository/server state; this file is context, not proof that anything still exists or is healthy.

## Mandatory startup procedure (every new session)

1. Read this checkpoint first.
2. Confirm repository, branch, latest commit, and working tree before editing.
3. Re-check relevant source files and tests. Do not assume prior claims are correct without source evidence.
4. If touching the server, inspect process, ports, health, environment and database paths first.
5. Never restart, modify, or deploy the primary Verigate service on port 8004.
6. Update this checkpoint after every meaningful code change, test run, deployment, blocker, or decision. Record exact commit SHA, commands, results, and what remains.
7. Never claim a task is complete unless the implementation and relevant tests have actually been verified.

## User goal

Complete a real Arc Mainnet USDC transfer where Verigate authorizes the exact transaction, the user's existing EVM wallet signs it locally, the transaction is broadcast, and the receipt is independently verified.

No Verigate-authorized live Arc transfer has been confirmed yet. Do not present another project's transaction as Verigate evidence.

## Existing wallet

Known EVM address:
`0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C`

Do not ask the user to repeat this address unless source/runtime evidence shows it is wrong or a different address is explicitly needed (for example, a recipient).

Never request, print, transmit, or store the EVM private key. Wallet signing must remain on the user's machine / wallet provider.

## Arc Mainnet facts previously verified

- Chain ID: `5042`
- RPC: `https://rpc.mainnet.arc.io`
- Explorer: `https://explorer.arc.io`
- ERC-20 USDC: `0x3600000000000000000000000000000000000000`
- ERC-20 USDC decimals: `6`
- Native gas asset is also USDC, but native gas denomination uses 18 decimals. Do not confuse it with ERC-20 transfer units (6 decimals).

## Architecture findings (source inspection)

- `core/identity.py`: agent ActionIntent signatures use Ed25519.
- `AgentIdentity` in `core/models.py` currently carries Ed25519 public key material and key ID; no dedicated wallet-address field was found in the inspected model.
- Arc authorize API requires `identity_id`, `capability_id`, and `agent_signature`.
- The inspected code did not show an EIP-191 / `personal_sign` / EIP-712 wallet-ownership challenge flow.
- Arc adapter validates/builds an ERC-20 transfer envelope; that alone does not prove that the sender address belongs to the registered agent.
- Existing Arc API tests register Ed25519 identities and capabilities directly in test storage.
- Therefore: EVM wallet ownership proof and Ed25519 ActionIntent signing are distinct. An EVM address cannot produce an Ed25519 signature. Do not silently treat an address as an Ed25519 key.

## Key handling — do not repeat previous mistake

A separate Ed25519 keypair was generated locally in an earlier attempt:
- identity ID: `2f8ff6451d207ed0e7256eea3561e4e3b606ea5ee9f836de744efed552908b67`
- public key (base64): `NoQA7esluOABZhJYO7LsSKwAc5CI2WM+FGkS+FU4cMY=`
- private key path on user's Windows machine: `C:\\Users\\User\\.verigate\\arc-agent\\agent-private.key`

This key was NOT registered in the isolated server DB according to the last inspection. Do not register it or generate another key without first proving it is necessary and obtaining the user's approval. Never expose private-key contents.

## Server isolation and safety

Previously observed server state (must re-check before use):
- Primary service: `/opt/verigate`, API port `8004`, PID previously `3958818`. **Do not touch/restart.**
- Isolated Arc copy: `/opt/verigate-arc-test`, API port `8005`, PID previously `3953000`.
- Isolated DB: `/opt/verigate-arc-test/runtime/arc-test.db`.
- Isolated API was loopback-only and health returned OK at last check.
- Isolated DB had 0 identities and 0 capabilities at last check.
- No API auth environment variables were found in the isolated process at last check. Do not expose port 8005 via Nginx/public interface until authentication is configured and verified.
- Never change Nginx, port 8004, or the primary project as part of this task.

These are historical observations, not current guarantees. Re-check before any server action.

## Current GitHub state

- Repository: `rudimentall1/verigate`
- Branch created: `feat/evm-wallet-identity-arc`
- The branch was created from `main` during this session.
- No implementation code has been changed yet.
- No tests have been run as part of the wallet-linking implementation.
- No server deployment or live transaction has been performed.

## Required implementation work

Implement and test a wallet-ownership binding without replacing the existing Ed25519 intent-signature protocol:

1. Review current identity, storage, API schema, engine, and authorization flows in the branch before designing the migration.
2. Add a short-lived, single-use EVM ownership challenge bound to the expected wallet address, chain/context, expiry, and nonce.
3. Verify an Ethereum-compatible personal-sign / EIP-191 signature using a well-supported library already present or a deliberately reviewed dependency. Normalize addresses safely; reject malformed signatures, wrong signer, expired challenge, replay, and cross-address substitution.
4. Persist an explicit verified wallet binding to the identity (or a normalized wallet-binding table with uniqueness/revocation semantics). Do not infer ownership from the `from` field in a transaction.
5. Make Arc authorization verify that the ERC-20 transaction sender equals the active wallet bound to the authorized identity. Bind sender, recipient, token, chain ID, amount and calldata to the signed authorization.
6. Keep Ed25519 ActionIntent signing intact unless a separately reviewed protocol migration is justified. Do not claim wallet signing replaces Ed25519.
7. Add tests for valid challenge, wrong signer, altered message, expiry, replay, duplicate binding, revoked binding, wrong transaction sender, wrong chain, wrong token, wrong recipient, and amount/calldata tampering.
8. Run targeted tests, then the full relevant test suite. Record exact commands and outputs.
9. Review API auth posture before exposing any endpoint. Keep test API loopback-only.
10. Only after code/tests are complete, prepare an isolated deployment plan. Do not deploy or send funds without explicit user approval.

## Transaction safety

- Do not broadcast a transaction during development/tests.
- Do not invent a recipient. The known address above is the user's existing wallet; whether it is sender or recipient must be established from the intended transaction.
- Before any live transaction, present exact chain, token contract, sender, recipient, amount, fee/gas handling, and authorization/execution sequence. Obtain explicit approval.
- Wallet must sign locally. Verigate must not custody the EVM private key.

## Required checkpoint update format

Append a dated entry below after each work session:
- What changed (file paths)
- Commit SHA / branch
- Tests run and exact pass/fail counts
- Server changes (or explicitly: none)
- Live transactions (or explicitly: none)
- Remaining blockers / next concrete action

## Session log

### 2026-11-07
- Inspected Arc integration and identity-related source/tests in GitHub.
- Confirmed Ed25519 ActionIntent signature flow; no wallet ownership challenge flow found in inspected source.
- Created branch `feat/evm-wallet-identity-arc`.
- No implementation files changed; no tests run; no server changes; no live transactions.
- Next action: inspect full identity/storage/API/engine flow on the new branch, then implement wallet challenge + binding with tests.

### 2026-11-07 — checkpoint synchronization and repository-state inspection
- Created the checkpoint on the isolated server at `/opt/verigate-arc-test/docs/SESSION_CHECKPOINT.md` and on the Windows workstation at `C:\\Users\\User\\Desktop\\Work\\verigate\\verigate\\docs\\SESSION_CHECKPOINT.md`.
- SHA256 verified identical on both machines: `563968bbab4f9e3086517488e6448d9450256f94471c652935d343cfda15329d`.
- Server `/opt/verigate-arc-test`: detached HEAD at `2957038` (`origin/main`); untracked `docs/SESSION_CHECKPOINT.md` and `runtime/`; isolated API on `127.0.0.1:8005` returned `{"status":"ok"}`; primary API remains on `127.0.0.1:8004`. No server files other than the checkpoint were changed.
- Workstation repo is on `fix/authority-ceiling-decimal-strings`, local HEAD `15f3dc5`, tracking branch reports 6 commits behind; checkpoint is untracked.
- GitHub `feat/evm-wallet-identity-arc` is exactly one commit ahead of `main` (checkpoint-only); no implementation changes exist on it.
- The workstation branch and the checkpoint branch have diverged histories (comparison from local HEAD `15f3dc5`: feature branch 62 commits ahead and 10 behind; merge base `d8453033ea9842b3431a640e553605a5e4f7e5c4`). Do not merge, reset, rebase, or switch branches until the workstation-only commits and required code are reviewed.
- Source review on the checkpoint branch confirms existing Ed25519 identity/action signatures, Arc transaction envelope construction, and Arc API tests that register an identity/capability directly; no EVM ownership proof is present in the inspected files.
- Tests run in this session: none. Code changes: none. Server deployment: none. Live transactions: none.
- Next action: inspect the workstation's 10 commits not on the feature branch and compare the complete local diff; choose a safe integration base before editing wallet-binding implementation.
