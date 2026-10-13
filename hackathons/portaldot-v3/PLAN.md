# Portaldot V3 Hacker House 2026

Status: preparation only. As of October 13, 2026, no PortalDot adapter or contract has been implemented or deployed by this project.

## Preparation documents

- [Verigate reuse audit](REUSE_AUDIT.md): source map, what to reuse, security boundaries and integration recommendation.
- [First build day checklist](START_TOMORROW.md): new-repository setup, contract scope, tests, checkpoints and submission checklist.
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

The contest implementation belongs in a **new public repository**, tentatively `rudimentall1/verigate-portaldot`. This Verigate folder remains the plan/audit index. Do not copy the Verigate core, router, database, API or signing implementation into a competing fork. Do not change core behavior solely for this event.

Expected new-repository layout:

- `contracts/`: one narrowly scoped demo treasury/action contract.
- `scripts/`: RPC preflight, deployment, demo and evidence collection.
- `src/`: Verigate authorization bridge and PortalDot RPC client.
- `test/`: contract tests and bridge/end-to-end security tests.
- `docs/`: architecture and threat model.
- `evidence/`: verified deployment data, transaction hashes and demo notes. Never put secrets here.

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
3. Create the new public repo and start its in-period development history on October 14.
4. Compile a minimal contract with Solidity `0.8.24`; add local contract tests.
5. Implement the Verigate-to-EIP-712 bridge and verify the exact signed action fields.
6. Test ALLOW, BLOCK with zero broadcasts, signature mutation, action mutation, replay, expiry, wrong chain/domain and wrong target.
7. Deploy to PortalDot V3, check contract address and transaction receipt, then independently verify on-chain state.
8. Record source commit, deployed contract address, transaction hashes and exact reproduction commands only after verification.
9. Prepare architecture, limitations, runnable demo, video and pitch deck.

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

- [ ] RPC returns chain ID 420420777 and a current block number.
- [ ] H160-to-SS58 mapping is checked and the correct account funded.
- [ ] Contract compiles and local tests pass.
- [ ] Bridge verifies the real Verigate Ed25519 authorization before issuing EIP-712.
- [ ] ALLOW performs the intended operation; BLOCK and all tampering/replay/expiry cases are rejected.
- [ ] PortalDot testnet deployment and receipt are independently verified.
- [ ] README has exact reproducible install/test/deploy/demo commands.
- [ ] Architecture and threat model explain the bridge trust boundary.
- [ ] Deployment address, transaction hashes and screenshots reflect real verified results.
- [ ] At least three meaningful in-period commits are present.
- [ ] Check-in/final submission artifacts meet the current official rules.
- [ ] No secrets are committed.

## Known limitations before implementation

- No PortalDot deployment address or transaction hash is recorded yet.
- The live RPC endpoint has not been verified from this audit environment.
- No adapter, bridge or contract for this submission has been implemented.
- Testnet behavior is not evidence of mainnet readiness or an independent security audit.
