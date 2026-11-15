# Verigate Reactive Execution Guard

**An AI agent should not be able to turn a payment instruction into an unrestricted transfer.**

Verigate makes the authorization decision before execution. It binds an approval to the exact action: who is acting, who gets paid, how much, where the payment goes, and how long the permission remains valid. Reactive carries that boundary from the origin chain to the destination chain, where a receiver checks the same commitment before moving funds.

This is the point of the project: **the agent can request a payment, but it cannot quietly change the payment after approval.**

## Why this belongs in the Reactive buildathon

A policy check in an application is not enough. It can be bypassed, become stale, or be separated from the transaction that eventually moves the funds. The check has to survive the trip to the chain where the side effect happens.

Reactive is the enforcement link in this demo. It observes the origin-chain authorization and execution request, compares the requested action with the committed recipient, amount, destination, issuer and expiry, then requests a destination callback only when the values match. A changed request is blocked before the receiver is called.

Without Reactive, this design would need a separately operated service to watch the origin chain and relay execution decisions. Here, the Reactive contract is part of the enforcement path, not just an alerting service.

## The demo

`Base Sepolia → Reactive Network (Lasna) → Unichain Sepolia`

1. Verigate returns a signed ALLOW receipt and a short-lived Ed25519 execution authorization.
2. A bridge adapter verifies both artifacts and prepares an issuer-signed origin-chain registration. The EVM issuer is an explicit trust boundary; the Solidity contracts do not verify Ed25519.
3. The origin hub publishes the exact authorization commitment.
4. Reactive observes and caches it, then checks the later execution request against that commitment.
5. Only a matching request can trigger the destination callback.
6. The destination receiver authenticates the callback, checks replay and expiry, recomputes the commitment, and transfers the exact amount to the approved recipient.

The receiver is a pre-funded testnet execution vault. It demonstrates a bounded on-chain side effect; it is not presented as a production non-custodial wallet.

## What is verified now

The origin authorization and execution-request transactions have succeeded on Base Sepolia. The destination receiver is deployed on Unichain Sepolia. A fresh Verigate ALLOW authorization for a 0.0001 ETH test payment was registered, and the issuer submitted the corresponding execution request.

**The final destination payment is not yet verified.** We do not claim a completed cross-chain payment until a destination transaction and `PaymentExecuted` event are independently confirmed. `ActionAllowed` on Reactive would prove that Reactive accepted the request and asked for a callback; it would not, by itself, prove that funds moved.

See [the technical checkpoint](integrations/reactive-omni/STATUS.md) for addresses, transaction hashes, tests, and the remaining evidence gap. See [the submission brief](integrations/reactive-omni/SUBMISSION.md) for the judge-facing explanation.

## Code and verification

The buildathon implementation is in [`integrations/reactive-omni/`](integrations/reactive-omni/README.md):

- [Origin authorization hub](integrations/reactive-omni/src/VerigateOriginAuthorizationHub.sol)
- [Reactive guard](integrations/reactive-omni/src/VerigateReactiveGuard.sol)
- [Destination payment receiver](integrations/reactive-omni/src/VerigatePaymentReceiver.sol)
- [Signed authorization bridge preparer](integrations/reactive-omni/prepare_registration.py)
- [Technical checkpoint and evidence](integrations/reactive-omni/STATUS.md)
- [Submission brief](integrations/reactive-omni/SUBMISSION.md)

The integration uses Foundry and pins the Reactive Omni Solidity library to `3ade0dcf1d27e67e5783ef807e73a1b9e0c0cce8`. Build and test instructions are in the integration README. CI runs the Python bridge checks, deployment-script syntax check, Solidity build, and Foundry tests.

**Verigate decides. Reactive enforces. The destination contract executes only the committed action.**
