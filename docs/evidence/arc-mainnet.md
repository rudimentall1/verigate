# Arc Mainnet evidence

This page records the team's existing Arc Mainnet deployment and transaction evidence, and distinguishes it from Verigate's Arc integration.

## Existing live deployment: Agentic Wallet Guardian v3

The team deployed **Agentic Wallet Guardian v3** with a live Arc Mainnet USDC payment demo. This is a related project by the same team; it is not a deployment of the Verigate service.

- Repository: https://github.com/rudimentall1/agentic-wallet-guardian-v3
- Live Arc demo: http://77.239.125.37:8765/arc
- Demo video: https://youtu.be/srH0ZLwtwqQ
- Network: Arc Mainnet
- Chain ID: `5042`
- RPC: https://rpc.mainnet.arc.io
- USDC ERC-20 contract: `0x3600000000000000000000000000000000000000`
- USDC ERC-20 decimals: `6`

### Verified mainnet transaction

The following USDC transaction was successfully executed on Arc Mainnet through the Agentic Wallet Guardian v3 demo:

```text
0xd781e8b04b5ca89c3a34fcec50a6636049f7647d2b0e1b2bb64d5b1ee54daadf
```

The Guardian repository README documents the live demo and this transaction. The demo evaluates the payment before the connected wallet signs and broadcasts it. Guardian does not custody the wallet or hold its private keys.

## Verigate's Arc integration

Verigate now has a separate first-party Arc Mainnet integration in the main repository:

- Integration guide: [docs/arc-mainnet-integration.md](../arc-mainnet-integration.md)
- Implementation PR: https://github.com/rudimentall1/verigate/pull/21
- Network configuration: Arc Mainnet, chain ID `5042`, official RPC and canonical USDC contract.
- Read-only status endpoint: `GET /v1/integrations/arc/status`
- Signed payment authorization endpoint: `POST /v1/integrations/arc/authorize`
- Execution authority is consumed through `POST /v1/execution/consume` before the client wallet signs and broadcasts the exact transaction.

The Verigate adapter reuses the validated Arc network parameters and non-custodial wallet flow, but performs authorization through Verigate's own signed ActionIntent, identity, capability, policy and execution-consumption path.

## Scope and attribution

The mainnet transaction above is **Guardian v3 evidence**, not a transaction authorized by Verigate. Verigate's Arc integration is implemented in the repository, but this evidence page does not claim that the Verigate adapter itself has been deployed to the live Guardian demo or that a Verigate-authorized mainnet transaction has occurred.

This distinction is intentional so reviewers can verify the team's existing Arc Mainnet experience without confusing the two codebases.
