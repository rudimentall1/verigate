# Verigate Reactive Omni

This integration puts an execution boundary between an AI agent's payment request and the transaction that actually moves funds.

The problem is concrete: an agent may be allowed to pay a supplier, but that permission must not let it swap the recipient, increase the amount, redirect the chain, or reuse an old approval. Verigate binds the decision to one exact action. Reactive carries that commitment across chains and checks the execution request where the destination callback is triggered.

**Verigate decides whether the action is authorized. Reactive enforces that commitment across chains. The destination receiver performs the bounded transfer.**

## Demo route

`Base Sepolia (84532) → Reactive / Lasna (5318007) → Unichain Sepolia (1301)`

1. Verigate returns a signed ALLOW receipt and short-lived Ed25519 `ExecutionAuthorization`.
2. The bridge preparer verifies the receipt and authorization, confirms they describe the same exact action, and prepares a wallet-signable registration transaction.
3. The enabled EVM issuer registers the commitment on the Base Sepolia Origin Hub.
4. Reactive observes the origin event and caches the commitment on Lasna.
5. The same issuer requests execution. Reactive compares the request against the cached recipient, amount, issuer, destination, expiry, revocation and replay state.
6. A matching request triggers a callback to the Unichain Sepolia receiver. A mismatch is blocked on Reactive and must not trigger a destination transfer.
7. The receiver authenticates the callback proxy and configured Reactive sender, recomputes the commitment and transfers only the approved amount.

The destination receiver is a **pre-funded testnet vault**. It is an execution proof, not a production non-custodial wallet.

## Why Reactive is necessary here

A normal application-side policy check does not protect the eventual on-chain side effect. Between approval and execution, a request can be changed, replayed or routed elsewhere. This integration uses Reactive as the event-driven enforcement layer between the origin-chain authorization and destination-chain callback. Without it, a separate operator-run watcher/relayer would have to implement that monitoring and decision path. Reactive is part of the enforcement design, not an alert feed.

## Cryptographic trust boundary

Verigate signs its authorization with Ed25519. The Solidity contracts do **not** verify Ed25519 on-chain.

The allowlisted EVM issuer is a bridge attester. Before it publishes an authorization, the bridge adapter verifies:
- the Ed25519 execution-authorization signature;
- the ALLOW decision receipt and its digest binding;
- the exact action and authorization fields;
- the supported destination network, asset, recipient and amount;
- expiry and required capability/authority/policy bindings.

The on-chain commitment binds the origin chain and hub, issuer, authorization ID, Verigate action/policy/receipt digests, destination chain and receiver, recipient, exact wei amount and expiry. This boundary is deliberate and must not be described as native on-chain Ed25519 verification.

## Current deployment and evidence

See [STATUS.md](STATUS.md) for the complete checkpoint, transaction hashes, test results and remaining gates.

Confirmed origin transactions:
- Base Sepolia authorization registration: `0xded94bd71d829c91bc914acef6e62f0dfbc99dcf2e08084115e9026ce8bc3a97`
- Base Sepolia execution request: `0x1b4b855d1229c27ca725371c9be3b54e98b95ada13ac0eaa36f7caf2760685b9`

Deployed addresses currently recorded:
- Origin Hub on Base Sepolia: `0x05d23191f063D704A3D2e367D5C268f1B5834637`
- Destination Receiver on Unichain Sepolia: `0xF1C8af8dA8c0cFe23ad04ca73533EF0AdE1B85B4`
- Unichain callback proxy: `0x775c9B990ADe401060B78D0e98684eEf8d2466C1`

The Reactive Guard deployment transaction is recorded in STATUS.md, but its address still needs to be extracted from the receipt. The destination `PaymentExecuted` event has not yet been confirmed. Therefore this repository does not claim a completed cross-chain payment.

## Build and test

From this directory:

```bash
git clone https://github.com/Reactive-Network/reactive-lib-omni.git lib/reactive-lib-omni
git -C lib/reactive-lib-omni checkout 3ade0dcf1d27e67e5783ef807e73a1b9e0c0cce8
forge build
forge test -vv
```

The Reactive library revision is pinned. CI also runs Python bridge tests, deployment-script syntax validation, Solidity compilation and Foundry tests.

## Prepare a Verigate authorization

The preparer accepts the full JSON response from `POST /v1/actions/authorize`, including both `decision_receipt` and `execution_authorization`. It verifies signatures and action/digest binding, checks the target hub and enabled issuer, then prepares a transaction for an EVM wallet to sign. It does not accept, store or broadcast an EVM private key.

```bash
python integrations/reactive-omni/prepare_registration.py authorization-response.json \
  --public-key /path/to/verigate-issuer-public.pem \
  --origin-hub "$VERIGATE_REACTIVE_ORIGIN_HUB" \
  --issuer "$VERIGATE_REACTIVE_EVM_ISSUER" \
  --destination-receiver "$VERIGATE_REACTIVE_DESTINATION_RECEIVER" \
  --rpc-url "$VERIGATE_REACTIVE_ORIGIN_RPC_URL"
```

The currently supported mapping is a payment in ETH on `unichain-sepolia`, with an EVM recipient and an exact decimal amount convertible to wei.

## Contract responsibilities

- `src/VerigateOriginAuthorizationHub.sol`: issuer-gated authorization registration, one-time IDs, revocation, destination-bound commitment and issuer-bound execution requests.
- `src/VerigateReactiveGuard.sol`: Reactive subscriptions, authorization cache, exact action/issuer checks, expiry, revocation, replay protection, BLOCK evidence and callback request.
- `src/VerigatePaymentReceiver.sol`: callback authentication, commitment recomputation, one-time execution and destination payment event.

`ActionAllowed` means Reactive accepted the request and submitted a callback request. It is not payment proof. Only a successful destination transaction with `PaymentExecuted` proves the transfer.

## Reactive buildathon dashboard

The dedicated browser dashboard is served by the existing Verigate API at:

`/demo/reactive/`

It signs the agent's exact payment intent locally with the registered Ed25519 identity key, submits the signed request to `POST /v1/actions/authorize`, and displays the real DecisionReceipt and ExecutionAuthorization response. The private agent key is not transmitted or persisted by the page. The API key is held in page memory and sent only as a Bearer credential to the same origin.

The dashboard does **not** broadcast the origin registration transaction, invoke the Reactive callback, or claim that the destination payment completed. When Verigate returns ALLOW plus an ExecutionAuthorization, download the JSON and pass it to `prepare_registration.py` as described above. The EVM issuer remains a separate bridge-attestation boundary.

Open it after deploying the updated API:

`http://127.0.0.1:8002/demo/reactive/`

Use HTTPS or localhost so browser Ed25519 WebCrypto is available. Supply the registered agent identity's PKCS#8 Ed25519 private key, the matching identity/capability IDs, and a Verigate API key. Never paste the issuer or deployer key into the dashboard.
