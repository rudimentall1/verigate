# Verigate Reactive Execution Guard

**Stop unauthorized AI-agent payments before they execute.**

An AI agent may have permission to make a payment, but that does not mean it should be able to change the recipient, exceed the approved amount, or reuse an old authorization.

Verigate defines exactly what an agent is allowed to do. Reactive Omni turns that decision into an on-chain execution boundary across chains: it watches authorization events, checks the requested action against the approved commitment, and requests a destination callback only when the request matches.

**Verigate defines authority. Reactive Omni enforces it across chains. The destination contract controls the final transfer.**

## Why Reactive Omni is essential

A signed authorization in an application is not enough. The permission has to be enforced where the blockchain side effect happens.

Reactive Omni supplies the event-driven link between the origin-chain authorization and the destination-chain callback. Without it, this cross-chain enforcement would require a separate service to watch the origin chain and initiate destination execution. Here, the Reactive Contract is an actual enforcement component, not a notification layer.

## Target demonstration

`Base Sepolia → Reactive Omni / Lasna → Unichain Sepolia`

- **ALLOW:** Verigate issues an authorization for a specific recipient and amount. Reactive verifies the on-chain commitment and requests a callback. The destination receiver authenticates the callback, checks the same commitment, and executes the payment once.
- **BLOCK:** A request with a changed recipient or amount is rejected by the Reactive Contract. It emits `ActionBlocked` evidence and does not request a destination callback.

The destination receiver is currently designed as a pre-funded testnet vault. It is an execution proof, not a production non-custodial wallet.

## Implementation

The buildathon integration lives in [`integrations/reactive-omni/`](integrations/reactive-omni/README.md):

- [Origin authorization hub](integrations/reactive-omni/src/VerigateOriginAuthorizationHub.sol)
- [Reactive Omni guard](integrations/reactive-omni/src/VerigateReactiveGuard.sol)
- [Destination callback receiver](integrations/reactive-omni/src/VerigatePaymentReceiver.sol)
- [Verigate authorization bridge preparer](integrations/reactive-omni/prepare_registration.py)
- [Technical status and evidence boundary](integrations/reactive-omni/STATUS.md)

## Cryptographic trust boundary

Verigate currently signs execution authorizations with Ed25519. The EVM contracts in this integration do not verify Ed25519 on-chain.

An allowlisted EVM issuer is therefore a bridge attester. Before publishing an origin-chain authorization event, the bridge adapter verifies the complete Verigate ALLOW receipt and execution authorization against the Verigate public key, checks the exact action and expiration, and prepares a wallet-signable EVM transaction. The adapter does not receive or store the EVM private key.

This boundary is explicit in the code and documentation. It is not presented as native on-chain Ed25519 verification.

## Build and tests

The integration uses Foundry and a pinned revision of the official [Reactive Omni Solidity library](https://github.com/Reactive-Network/reactive-lib-omni).

From `integrations/reactive-omni/`:

```bash
git clone https://github.com/Reactive-Network/reactive-lib-omni.git lib/reactive-lib-omni
git -C lib/reactive-lib-omni checkout 3ade0dcf1d27e67e5783ef807e73a1b9e0c0cce8
forge build
forge test -vv
```

The current source includes unit tests for issuer restrictions, exact authorization commitments, callback authentication, expiry, replay, modified payment parameters, and bridge transaction encoding. Check the [status file](integrations/reactive-omni/STATUS.md) and [GitHub Actions](https://github.com/rudimentall1/verigate/actions) for the latest verified result.

## Current status

**Implementation in progress. Not deployed.**

No live contract addresses, transaction hashes, Reactive callbacks, or testnet payment results are claimed yet. The immediate next milestone is a clean CI run, followed by deployment and an independently verifiable Base Sepolia → Lasna → Unichain Sepolia execution.

## Existing Verigate project

The broader Verigate authorization infrastructure is the dependency behind this buildathon integration. Its main project documentation is available on the [`main` branch](https://github.com/rudimentall1/verigate/tree/main).
