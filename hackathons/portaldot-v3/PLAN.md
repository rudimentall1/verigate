# PortaldotV3 Hacker House 2026

Status: planning and infrastructure discovery. This document does not claim that a Portaldot adapter or contract has been implemented or deployed.

## Network details

Details below were supplied in the PortaldotV3 official developer announcement and guide. Re-check them against the guide and organizer announcements before deployment.

| Setting | Value |
|---|---|
| EVM RPC | https://testnetv3-eth-rpc.feso-apps.xyz |
| Chain ID | 420420777 |
| Substrate RPC | wss://testnetv3-node.feso-apps.xyz |
| Node explorer | https://node-console.feso-apps.xyz/ |
| Native test token | tPOTv3 |
| Native token decimals | 14 |
| Official developer guide and samples | https://github.com/ItsCogumellum/portaldot-v3-testnet-guide |

The guide covers Substrate queries and signing, native fungible assets, Uniques/NFTs, and Solidity development through MetaMask, Hardhat, Remix, and Portaldot tooling.

### Critical address-mapping warning

The H160 address derived from an EVM key is not necessarily the Substrate account address used to fund the same account. Before funding a deployer, follow the guide's Developer → Runtime calls → reviveApi → accountId procedure and verify the mapping. Do not send funds based only on the Ethereum-style address.

Never commit a private key, seed phrase, .env file, RPC credential, or funded-wallet material.

## Product goal

Demonstrate Verigate's existing authority model in a real PortaldotV3 EVM transaction flow:

> An agent can propose an operation, but execution only proceeds when the exact operation has valid authority. The resulting evidence must be independently inspectable.

The Portaldot integration must be a small, clearly scoped adapter and demo. It must not redefine Verigate or imply that the entire Verigate protocol runs on-chain.

## Isolation boundary

Keep all Portaldot-specific work under this directory. Expected implementation layout:

- contracts/: a minimal demo target and, if justified by the design, a narrowly scoped authorization guard.
- scripts/: network checks, deployment, address verification, and demo scenarios.
- test/: allow, deny, replay, expiry, and tampering tests.
- src/ or adapter/: Portaldot-specific EVM submission/receipt adapter.
- evidence/: verified deployment metadata, transaction hashes, screenshots, and demo notes. Never put secrets here.
- PLAN.md: this plan and progress record.

Do not copy Verigate core, router, or signing implementation into a competing fork. Reuse the existing project through a documented integration boundary. Do not change core behavior solely to satisfy the hackathon.

## Security design requirements

Before choosing the final contract boundary, inspect Verigate's current authorization format and threat model.

- Bind authorization to the chain ID, verifying contract, exact target, value, calldata or a collision-resistant calldata hash, nonce, and deadline.
- Use a signature scheme the on-chain verifier actually supports. Verigate's existing Ed25519 decisions cannot be assumed to be directly verifiable by an ordinary Solidity contract. If the demo uses an EIP-712 authorization bridge, document the signer trust boundary and how the bridge is authorized.
- Reject replayed, expired, altered, wrong-chain, and wrong-target authorizations.
- Avoid an unrestricted target.call interface controlled by caller-supplied expected values or caller-selected oracles.
- Do not claim that an off-chain decision is enforced on-chain unless the contract or a clearly identified trusted execution boundary really enforces it.
- Do not treat a successful deployment as a security audit.

## Implementation sequence

1. **Verify network connectivity.** Query eth_chainId and compare it with 420420777; read the latest block; record the date and command output.
2. **Validate wallet mapping and funding.** Follow the official reviveApi.accountId instructions. Confirm the mapped address before requesting or sending test tokens.
3. **Prove the toolchain.** Compile, test, and deploy a minimal isolated Solidity contract with Hardhat. Verify the deployed address and transaction in the explorer.
4. **Implement one meaningful guarded action.** Keep the example small enough to explain in a three-minute demo. Prefer a specific state change over an unrestricted generic call executor.
5. **Test adversarial cases.** Include valid authorization, denied action, altered calldata, replay, expiry, wrong chain/domain, and wrong target. Add fuzzing/property tests if supported by the chosen stack.
6. **Verify evidence.** Store contract addresses, deployment transaction, test output, source commit, and reproducible commands. Mark every item as pending until it has actually been checked.
7. **Prepare the submission.** Provide architecture, setup/deployment instructions, limitations, attribution, and a demo no longer than the event's stated limit.

## Event milestones to confirm

The working timeline collected from the event listing is:

- Build period: October 14 to November 6, 2026.
- Check-in / registration milestone: October 24, 2026; verify the exact prototype and registration requirements on the official event page.
- Code freeze: November 6, 2026.
- Demo day: November 7–8, 2026.
- Community voting: November 8–9, 2026.
- Awards: November 10, 2026.

The event materials indicate that the repository should be public, the work should include at least three substantive commits during the hackathon, and a public testnet deployment and concise demo are expected. Confirm the exact current rules with organizers. Existing open-source components may be reusable with attribution, but do not present pre-existing Verigate functionality as newly built hackathon work.

## Definition of done

- [ ] PortaldotV3 RPC returns chain ID 420420777.
- [ ] Deployer H160-to-account mapping has been checked using the official guide.
- [ ] Isolated contract compiles and tests pass.
- [ ] Contract is deployed to PortaldotV3 testnet and verified in the explorer.
- [ ] Allow and deny scenarios are demonstrated with transaction evidence.
- [ ] Replay and tampering tests demonstrate rejection.
- [ ] No secrets are committed.
- [ ] README includes exact reproducible commands, architecture, threat boundary, limitations, and attribution.
- [ ] Demo and submission satisfy the current official rules.

## Known limitations until implemented and tested

- No Portaldot deployment address or transaction hash is recorded here yet.
- No claim is made that the adapter, authorization guard, or demo has been built.
- Testnet behavior is not evidence of mainnet readiness or an independent security audit.
- The design must clearly distinguish off-chain Verigate authorization from any on-chain enforcement.
