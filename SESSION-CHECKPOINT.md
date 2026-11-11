# Verigate Session Checkpoint

**Updated:** 2026-11-11  
**Repository:** rudimentall1/verigate  
**Current work branch:** release/arc-security-consolidation-2026-11-11  
**Default branch:** main  
**Consolidation PR:** https://github.com/rudimentall1/verigate/pull/53  
**Current consolidation HEAD:** 97dda249bba431b94ccb54e66fd317d4ea616a4f  
**Main HEAD at branch creation:** 3731ae66c3ed9e8bd5ef36f0c00e48457db746c3

## 1. Current state

The Arc Authority Registry integration and the external agent SDK changes have been ported onto a branch created from current main. The branch compares as **88 commits ahead, 0 behind**, with 46 changed files at the latest comparison.

PR #53 is open and Draft. It has not been merged. The original PRs #38, #40, #41 and #42 remain unmerged; their stale/diverged branches were not blindly merged.

The current exact-head CI run is queued:
- Push run: https://github.com/rudimentall1/verigate/actions/runs/42995098307
- Exact head: 97dda249bba431b94ccb54e66fd317d4ea616a4f
- GitHub currently reports mergeability as unknown while calculating. Do not merge until exact-head CI is green and the final diff is reviewed.

Earlier security-container-only commit 1272b99be169c871054ef9588ef06011784e7105 passed all four jobs, including the new container job (Docker build and API authentication smoke test): https://github.com/rudimentall1/verigate/actions/runs/42993439289. This does not validate the later Arc and security changes on the current HEAD.

## 2. Arc integration now ported onto consolidation branch

Ported from PR #38:
- Arc Authority Registry Solidity contract.
- Arc-specific authorization, registration confirmation and consumption confirmation API endpoints.
- Signed Arc payment ActionIntent bound to sender, recipient, token, amount, chain and transfer calldata.
- Identity, capability and deterministic policy checks before executable authority is issued.
- Generic execution-consume route rejects Arc authorizations.
- Transaction, receipt, calldata, sender, destination, event topic, Registry state, block hash and timestamp verification.
- Local one-time authorization consumption only after on-chain Registry consumption is confirmed.
- EIP-1193 wallet client; payment broadcast remains a separate explicit user action.
- Agent SDK, enrollment script, Arc client, compilation script and regression tests.

Ported from PR #41:
- Late HTTP confirmation is accepted only when the canonical Arc inclusion timestamp was inside the signed authorization interval.
- Evidence page now separates Registry deployment, Guardian v3 payment evidence and any future Verigate-authorized payment.

Ported from PR #42:
- Generic public-only agent enrollment package.
- Operator-controlled enrollment/revocation script.
- Dependency-free HTTP client.
- Runnable external-agent example and quickstart.
- Client fails closed on non-ALLOW, malformed responses, transport failures and unsuccessful one-time consumption.

## 3. Arc finality

The Registry verification path now:
1. Fetches the receipt inclusion block by number.
2. Verifies its hash against the receipt block hash.
3. Fetches the RPC block tagged finalized.
4. Requires the inclusion height to be at or below the finalized head.
5. If the finalized head is the inclusion block itself, requires the hashes to match.

This uses Arc's deterministic finality model rather than imposing an arbitrary 12/20-confirmation rule. If the RPC does not support or return a valid finalized block, the flow fails closed. Runtime bytecode is pinned by Keccak hash and the configured executor must be an enabled issuer.

Arc's deterministic finality is a property of Arc settlement. Verigate cannot honestly claim transaction finality faster than Arc. Our separate performance targets are:
- local policy/identity/signature authority decision p95 <100 ms;
- server-side pre-broadcast path p95 <500 ms excluding user approval, wallet signing, RPC inclusion and Arc consensus finality.

These are targets only; no benchmark has yet been run.

## 4. Runtime bytecode pinning

The Arc Registry client now requires VERIGATE_ARC_REGISTRY_CODE_HASH and compares the Keccak-256 hash of deployed runtime bytecode to the configured expected hash. Missing or mismatched hash fails closed. Deployment verification also checks that the configured executor is an enabled issuer. It also verifies that the configured executor is an enabled issuer.

Added:
- pycryptodome dependency for Keccak-256 in the Python verification path.
- compile script outputs the reproducible runtime bytecode hash.
- scripts/verify_arc_deployment.mjs performs read-only checks: compile source, compare deployed runtime bytecode, verify chain ID, owner and finalized block, and print the exact environment variable value.

**Not yet completed:** the read-only verification script has not been run against Arc Mainnet in this session. The actual runtime hash has not yet been independently recorded or installed in the production service environment. Do not claim bytecode pinning is operational until that hash is verified and configured.

## 5. Production API and container security changes

The consolidation branch now includes:
- Protected API routes deny by default if API keys are not configured.
- The only unauthenticated development mode requires both VERIGATE_ENV=development and VERIGATE_ALLOW_INSECURE_DEV_MODE=1.
- Executable authority requires agent-signed intents outside that explicit development mode.
- Docker image defaults to production mode, API authentication, signed intents and encrypted issuer keys.
- Docker Compose requires API key and key passphrase and binds port 8000 to 127.0.0.1.
- Local workspace artifacts are excluded from Docker build context.
- Container CI validates the Compose config, builds the image and checks protected route 401 without key / 200 with key.
- Tests cover default-deny and explicit development opt-in.

The main branch is not yet changed. All of these changes remain in PR #53 until merge.

## 6. Confirmed security limitations still open

1. Issuer keys remain local-file based. Encrypted-at-rest storage does not protect a compromised running host. KMS/HSM or a dedicated signing service is not implemented.
2. No complete issuer-key rotation and emergency-revocation workflow.
3. Registry owner/issuer governance still needs multisig/timelock or equivalent operational protection.
4. The Registry is not escrow and does not block direct out-of-band wallet transfers. It enforces the integrated Verigate client path only.
5. Trusted handlers may create transitive child side effects outside the directly observed execution boundary.
6. SQLite is single-process storage; multi-replica service operation needs shared transactional storage or a production database.
7. Volumetric DoS and high-concurrency load testing have not been completed.
8. RPC provider is still a trust boundary. The finalized tag and canonical block hash checks are implemented, but no live Arc RPC verification has been performed on this exact branch.
9. No independent penetration test or third-party security audit has been completed.
10. No Verigate-authorized Arc registration/consumption/USDC payment has been independently verified.

## 7. Registry deployment facts and attribution

Previously user-confirmed deployment facts:
- Arc Mainnet, chain ID 5042.
- Registry: 0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D.
- Deployment tx: 0xe85784e81ca0069410e8555961c8403fa02adc1361c7455657106afc96855ebb.
- Block: 30012679.
- Owner/executor: 0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C.

These facts are user-confirmed historical deployment evidence. They have not been freshly reverified on Arc in this session.

The transaction 0xd781e8b04b5ca89c3a34fcec50a6636049f7647d2b0e1b2bb64d5b1ee54daadf belongs to Agentic Wallet Guardian v3, not Verigate. Never attribute it to Verigate.

## 8. Immediate next steps

1. Inspect current exact-head CI run #42994567549 and fix all failures before adding further features.
2. Run npm run verify:arc-deployment against Arc Mainnet; record the output and independently inspect the runtime hash. Do not deploy or send transactions.
3. Configure VERIGATE_ARC_REGISTRY_CODE_HASH in the intended API environment only after independent verification.
4. Add explicit tests for missing/unsupported finalized tag, receipt block above finalized head, finalized hash mismatch, and recovery after Registry consumed/local nonce failure.
5. Add adversarial API tests for tenant confusion, unsigned capability, replay/race, identity tampering and direct execution bypass.
6. Add a reproducible latency benchmark and report p50/p95/p99; do not weaken checks to hit the target.
7. Review the entire PR #53 diff for accidental changes and unsupported claims.
8. Merge PR #53 only when exact-head CI is green and the diff is reviewed. Verify the resulting main SHA and new main CI.
9. After merge, independently verify Registry deployment and perform a live Verigate registration/consumption flow only with explicit operational approval. Payment broadcast requires separate explicit approval.

## 9. Hard boundaries

- No force-push and no blind merge of stale branches.
- No production server deployment/restart.
- No Registry redeployment or owner/issuer changes.
- No private-key export or wallet broadcast.
- No fabricated live payment evidence.
- No claim of unhackable, fully audited, global wallet-firewall or faster-than-Arc-finality behavior.
