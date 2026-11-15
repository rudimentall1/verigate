# Reactive Buildathon Submission Brief

## Project

**Verigate Reactive Execution Guard**

An AI agent should not be able to change a payment after it has been approved. Verigate binds permission to the exact recipient, amount and destination. Reactive checks that commitment across chains before the destination contract is allowed to move funds.

## The problem

Agents are moving from answering questions to taking actions: paying invoices, settling transactions and operating wallets. Giving an agent a wallet key or broad spending permission creates a simple failure mode: the agent can make a valid-looking request that sends the wrong amount to the wrong address.

A policy check in the app is not enough. The check must still be enforced when the blockchain transaction is executed, including when the action crosses chains.

## What we built

Verigate is the authority layer. It evaluates the action and produces a signed, short-lived authorization only when policy and authority checks allow it.

Reactive is the cross-chain enforcement layer. It observes the origin-chain commitment and execution request, checks that the issuer, recipient, amount, destination and expiry still match, and requests a destination callback only for the exact approved action.

The destination receiver authenticates the callback, checks the commitment again, blocks replay, and transfers only the approved amount.

## Why Reactive matters

Reactive is not being used as a notification service. Its contract sits in the enforcement path between the origin-chain authorization and the destination-chain side effect. It removes the need for a separately operated watcher/relayer to implement that event-driven cross-chain decision path.

The key property is simple: changing the recipient or amount after approval must not result in a payment.

## Demo architecture

`Base Sepolia → Reactive Network (Lasna) → Unichain Sepolia`

- Origin: `VerigateOriginAuthorizationHub`
- Reactive: `VerigateReactiveGuard`
- Destination: `VerigatePaymentReceiver`

## Security boundary

Verigate signs execution authorizations with Ed25519. The EVM contracts do not verify Ed25519 on-chain. An allowlisted EVM issuer acts as a bridge attester and must verify the signed Verigate receipt and authorization before publishing the origin-chain commitment. This trust boundary is explicit in the implementation.

The destination receiver is a pre-funded testnet executor, not a production non-custodial wallet.

## Evidence available at this checkpoint

- Base Sepolia Origin Hub deployed at `0x05d23191f063D704A3D2e367D5C268f1B5834637`.
- Unichain Sepolia Receiver deployed at `0xF1C8af8dA8c0cFe23ad04ca73533EF0AdE1B85B4`.
- A Verigate ALLOW authorization for a 0.0001 ETH payment to `0x4c07B4f328FA738290Db96BCE2F9CBc4d020D2CB` was registered on Base Sepolia.
- The issuer successfully submitted the matching `requestExecution` transaction on Base Sepolia.
- Transaction hashes and the Reactive Guard deployment transaction are recorded in [STATUS.md](STATUS.md).

## Honest status

The final Unichain callback and `PaymentExecuted` event have not yet been confirmed. The submission must not claim a completed cross-chain payment or measured full-loop latency until that evidence is captured. The Reactive Guard address also needs to be extracted from its deployment receipt.

## What the finished demo must show

1. A Verigate ALLOW authorization for a specific recipient and exact amount.
2. Origin registration and Reactive authorization caching.
3. Reactive acceptance of the exact request and a destination `PaymentExecuted` transaction.
4. A modified-recipient or modified-amount request blocked on Reactive, with no destination payment.
5. The measured time from origin event to destination execution, using the timestamps of the two on-chain transactions.

## Suggested opening line for the demo

“An AI agent can request a payment, but it cannot rewrite the payment after approval. Verigate defines the exact permission; Reactive enforces it across chains before funds move.”
