# Arc Mainnet evidence

This page separates three different claims: the team's earlier Arc payment demo, Verigate's deployed Arc Authority Registry, and a Verigate-authorized payment. They are not interchangeable.

## Verigate Arc Authority Registry deployment

Verigate's Arc Authority Registry was deployed to Arc Mainnet.

- Network: Arc Mainnet
- Chain ID: `5042` (`0x13b2`)
- Registry contract: `0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D`
- Deployment transaction: `0xe85784e81ca0069410e8555961c8403fa02adc1361c7455657106afc96855ebb`
- Deployment receipt status: `0x1` (successful)
- Deployment block: `30012679`
- On-chain owner: `0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C`
- RPC: https://rpc.mainnet.arc.io
- Explorer: https://explorer.arc.io

The deployment transaction and subsequent read-only RPC checks establish that the Registry contract has bytecode at the configured address, the connected RPC reports Arc chain ID 5042, and `owner()` returns the address above. These checks establish deployment and contract ownership; they do not establish that a payment was executed through Verigate.

## Verigate integration flow

The current implementation uses the Arc Authority Registry sequence documented in [the Arc integration guide](../arc-mainnet-integration.md):

1. `POST /v1/integrations/arc/authorize` validates the signed agent intent, identity, capability, policy and exact Arc USDC envelope, then returns an Execution Authorization and registration transaction.
2. The operator-controlled Registry issuer signer submits registration.
3. `POST /v1/integrations/arc/registration/confirm` verifies the issuer transaction, receipt, canonical inclusion block, Registry event and state.
4. The agent's own EVM executor submits the one-time consumption transaction. Its address is bound to the signed payment sender.
5. `POST /v1/integrations/arc/consume/confirm` verifies the executor transaction and Registry state before returning the exact USDC transaction.
6. The agent executor broadcasts the payment. `POST /v1/integrations/arc/payment/confirm` independently checks the Transfer event and finalized settlement.

The generic `POST /v1/execution/consume` route rejects Arc authorizations with HTTP 409 so it cannot bypass the Registry sequence.

## Separate team project: Agentic Wallet Guardian v3

The team also has a live Arc Mainnet USDC payment demo in a separate repository. This is not Verigate and its transaction must not be attributed to Verigate.

- Repository: https://github.com/rudimentall1/agentic-wallet-guardian-v3
- Live demo: http://77.239.125.37:8765/arc
- Demo video: https://youtu.be/srH0ZLwtwqQ
- Network: Arc Mainnet, chain ID `5042`
- Canonical USDC ERC-20: `0x3600000000000000000000000000000000000000`
- USDC ERC-20 decimals: `6`

Guardian v3 demo transaction:

```text
0xd781e8b04b5ca89c3a34fcec50a6636049f7647d2b0e1b2bb64d5b1ee54daadf
```

This transaction is evidence for Guardian v3 only.

## Evidence boundary and current limitations

- The Registry deployment is a confirmed Verigate on-chain deployment.
- Automated HTTP E2E tests exercise authorization, registration confirmation, consumption confirmation and the wallet-payment handoff using mocked RPC and wallet transactions.
- No Verigate registration or consumption transaction hashes are currently recorded here as live mainnet execution evidence.
- No live USDC payment authorized through Verigate is claimed.
- The Registry is an authority/evidence mechanism, not escrow and not a universal USDC transfer guard. Direct transfers submitted outside the compliant Verigate client flow are not prevented by this contract.
- The API verifies canonical inclusion block hashes and timestamps, but the implementation does not currently define an additional multi-block finality wait policy.
- The Registry stores the authorization ID, intent hash, executor, expiry and one-time consumed/revoked state; it does not store the full payment payload.

For grant and partner reviews, describe the Registry deployment, mocked end-to-end integration tests, Guardian v3 payment demo and any future Verigate-authorized payment as separate evidence items.


## Arc USDC settlement verification capability

A separate implementation branch adds `POST /v1/integrations/arc/payment/confirm` and an EIP-1193 client helper, `confirmArcPayment`. After the user explicitly broadcasts the wallet payment, the API can verify the transaction against the original signed authorization, the confirmed Registry consumption, the canonical USDC contract, the exact sender/recipient/amount Transfer event, the canonical inclusion block and Arc finalized head.

Implementation branch: `feat/arc-payment-settlement-confirmation-2026-11-12`.

This is currently **source-level implementation under CI review**. It has not been merged, deployed to a hosted Verigate API, or exercised with a live Verigate-authorized Arc USDC payment. No settlement transaction hash is claimed. The existing evidence boundary above remains unchanged until a real wallet transaction is broadcast and the new endpoint independently verifies its finalized receipt.
