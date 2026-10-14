# Portaldot V3 Hacker House 2026

Status: implementation scaffold committed on October 14, 2026. Public repo: [rudimentall1/verigate-portaldot](https://github.com/rudimentall1/verigate-portaldot). The contract, bridge-signing CLI and tests are in place; GitHub Actions passed 15 tests and Solidity compilation. Live RPC connectivity, Verigate end-to-end signing and PortalDot deployment are still unverified.

## Preparation documents

- [Verigate reuse audit](REUSE_AUDIT.md): source map, what to reuse, security boundaries and integration recommendation.
- [Build checklist and current state](START_TOMORROW.md): actual repo status, commands to run locally, and remaining network/integration gates.
- Parent [hackathon index](../README.md).

## Network details

Checked against the [official Portaldot V3 testnet guide](https://github.com/ItsCogumellum/portaldot-v3-testnet-guide) on October 13, 2026. Test connectivity and chain ID again before every deployment.

| Setting | Value |
|---|---|
| EVM RPC | https://testnetv3-eth-rpc.feso-apps.xyz |
| Chain ID | 420420777 |
| Substrate RPC | wss://testnetv3-node.feso-apps.xyz |
| Node explorer | https://node-console.feso-apps.xyz/ |
| Native test token | tPOTv3 |
| Native token decimals | 14 |
| Suggested initial Solidity version | 0.8.24 |
| Official developer guide and samples | https://github.com/ItsCogumellum/portaldot-v3-testnet-guide |

The guide covers Substrate queries and signing, native fungible assets, Uniques/NFTs, and Solidity development through MetaMask, Hardhat, Remix and Portaldot tooling.

### Critical address-mapping warning

The EVM H160 address and the mapped Substrate SS58/AccountId32 address must not be assumed identical. Before funding a deployer, follow the guide's **Developer → Runtime calls → reviveApi → accountId** procedure and verify the mapped SS58 address. Do not send test POT based only on an Ethereum-style address.

Never commit a private key, seed phrase, `.env`, RPC credential or funded-wallet material.

## Product goal

Demonstrate a verifiable authority check for one consequential agent action on PortalDot V3:

> An agent can propose an action, but execution only proceeds when the exact operation has valid authority. The result can be checked against actual PortalDot transaction evidence.

The integration must remain small and understandable. It must not redefine Verigate or imply the whole control plane runs on-chain.

## Repository boundary

The contest implementation now lives in the public repository [rudimentall1/verigate-portaldot](https://github.com/rudimentall1/verigate-portaldot). This Verigate folder remains the plan/audit index. Do not copy the Verigate core, router, database, API or signing implementation into a competing fork. Do not change core behavior solely for this event.

Current repository layout:
 
- `contracts/PortalDotAgentGuard.sol`: signed native-token transfer guard.
- `adapter/verigate-bridge.js`: initial Verigate response validation and EIP-712 signing CLI.
- `scripts/preflight.js`: PortalDot EVM RPC check for chain ID and latest block.
- `scripts/deploy.js`: network-guarded deployment command.
- `test/`: contract tests and bridge-binding tests.
- `docs/`: security boundary and bridge mapping.
- `evidence/`: deployment evidence placeholder; no live evidence recorded.

## Security design requirements

- Bind action authorization to chain ID, verifying contract, exact operation/recipient/amount or calldata hash, nonce and deadline.
- Use a signature scheme supported by Solidity. Verigate's existing authorization is Ed25519 and cannot be assumed directly verifiable by an ordinary Solidity contract.
- If the bridge validates Verigate's signed authorization off-chain and issues an EIP-712 signature, document the bridge signer as an explicit trust boundary. The bridge must verify the original signature, ALLOW outcome, expiry, nonce and all action fields before signing.
- Reject replayed, expired, altered, wrong-chain/domain and wrong-target authorizations.
- Prefer one fixed demo-token transfer operation over a generic caller-selected `target.call` relay.
- A BLOCK/WARN response must not produce a bridge signature or broadcast.
- Do not claim that an off-chain decision is enforced on-chain unless the contract or a named trusted boundary really enforces it.
- A successful testnet deployment is not a security audit.

## Existing Verigate components to reference

The [reuse audit](REUSE_AUDIT.md) maps the existing sources. Key seams are:

- `POST /v1/actions/authorize` in `api/main.py`: protocol-agnostic authority issuance for an agent-signed `ActionIntent`.
- `core/models.py`, `core/identity.py`, `core/capabilities.py`, `core/policy.py`: action shape, identity, capability and deterministic policy.
- `attest/receipt.py`: signed decision receipt and separate execution authorization.
- `enforcement/evm_rpc.py`, `enforcement/chain_verification.py`: EVM RPC and independent receipt observation patterns.
- `docs/threat-model.md`: current trust boundaries and known gaps.

Verigate's root repository has no root `pyproject.toml` publishing the entire runtime as an installable package. Do not document `pip install verigate` as a working integration unless that is separately created and tested. A local Verigate process/API or a documented checkout-based bridge is the more direct starting point.

## Implementation sequence

1. Query PortalDot `eth_chainId` and `eth_blockNumber`; stop if the chain ID is not `420420777`.
2. Confirm the H160-to-SS58 mapping using the official guide and fund the correct mapped account with test POT.
3. [x] Create the public repo and start its in-period history. Initial implementation commits are in `rudimentall1/verigate-portaldot`.
4. [x] Add the Solidity 0.8.24 native-payment guard and local tests. GitHub Actions passed the compile and test steps; 15 tests passed.
5. [~] Add the first Verigate-to-EIP-712 bridge CLI. It validates the ALLOW response shape, asks the configured Verigate verification endpoint to validate both Ed25519 artifacts, then signs the bounded EIP-712 transfer. It still needs a real-response end-to-end run.
6. [~] Add local checks for action binding, BLOCK/WARN refusal, replay, expiry, wrong chain, signature and recipient/amount mutation. End-to-end transaction/broadcast evidence remains outstanding.
7. [ ] Re-check PortalDot V3 RPC, chain ID and current block; the event team previously reported the RPC unavailable.
8. [ ] Confirm H160-to-SS58 mapping, fund the correct test account, deploy, and independently verify the transaction receipt and contract state.
9. [ ] Record only verified deployment evidence, then prepare the runnable demo, video and pitch deck.

## Official event milestones

From the [PortalDot Hacker House 2026 event page](https://dorahacks.io/hackathon/portaldot-hacker-house-2026/detail), checked October 13, 2026:

- **Kick-off and workshop:** October 14, 12:00–14:00 UTC.
- **Check-in submission deadline:** October 24, 12:00 UTC.
- **Feedback results:** October 26, 16:00 UTC.
- **Office-hours application deadline:** October 27, 12:00 UTC.
- **Office hours:** October 28–29 UTC.
- **Final submission / code freeze:** November 6, 04:00 UTC.
- **Live demo day:** November 8–9 UTC.
- **Community Choice voting:** November 9, 16:00 to November 10, 16:00 UTC.
- **Winners announced:** November 11 UTC.
- **Reward distribution:** November 14, 12:00 UTC.

Requirements include a public repository, at least three substantive commits during the event period, source code primarily produced during October 14–November 6, a running demo, deployment evidence where applicable, and a final demo video no longer than three minutes. The check-in should already show a prototype/core flow, not only an idea. See the event page for full submission and scoring requirements.

## Definition of done

- [x] Public implementation repository created and linked.
- [x] Contract, bridge-binding and negative-path tests committed.
- [x] GitHub Actions: 15 tests passed and Solidity compilation succeeded on commit `6c59a74f75fa2f01e72d45b1a193d71f60e22dfa`.
- [x] Local Windows checkout verified by the developer: `npm test` reported 15 passing; `npm run compile` reported nothing to compile.
- [ ] RPC returns chain ID 420420777 and a current block number. The developer's `npm run preflight` currently fails with `fetch failed`; no live network access is confirmed.
- [ ] H160-to-SS58 mapping is checked and the correct account funded.
- [ ] Run the bridge against a real response from the configured Verigate instance.
- [ ] Verify ALLOW performs the intended operation; BLOCK, tampering, replay, expiry and wrong-domain cases remain rejected end-to-end.
- [ ] PortalDot testnet deployment and receipt are independently verified.
- [ ] README has exact reproducible install/test/deploy/demo commands.
- [ ] At least three meaningful in-period commits are present.
- [ ] Check-in/final submission artifacts meet the current official rules.
- [ ] No secrets are committed.

## Known limitations

- No PortalDot deployment address or transaction hash is recorded.
- Live PortalDot RPC connectivity has not been confirmed. The developer also ran `npm run preflight`, which returned `fetch failed`.
- Bridge binding tests use fixtures. The CLI has not yet been run against a real Verigate API response.
- The contract trusts a dedicated EVM bridge signer; it does not verify Verigate's Ed25519 signature on-chain.
- Testnet behavior is not evidence of mainnet readiness or an independent security audit.


## Local Verigate API check (2026-10-14)

The developer started the local Verigate API from the `Work\\verigate\\verigate` checkout. `GET /health` returned `status=ok`, and the OpenAPI document listed `POST /v1/actions/authorize`, `POST /v1/verify`, `POST /v1/verify/adversarial`, and `GET /v1/public-key`.

The PortalDot repo now includes `scripts/verigate_local_demo.py`. It is designed to exercise a second loopback-only Verigate process on port 8001 with its own temporary policy, SQLite DB and throwaway issuer keys. It submits signed ALLOW/BLOCK actions, verifies the signatures, runs the bridge CLI with a disposable EVM signer and dummy contract domain, and asserts that BLOCK is refused. It does not use the normal Verigate DB or send transactions.

**Still outstanding:** the developer has not run this helper yet. A successful `/health` response from port 8000 confirms the API process is up, but does not by itself prove the PortalDot adapter end-to-end flow.
