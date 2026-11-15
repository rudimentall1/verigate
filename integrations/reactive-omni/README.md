# Verigate Reactive Omni Integration

**Track:** Set It and Forget It  
**Target flow:** Base Sepolia → Reactive Omni / Lasna → Unichain Sepolia

This directory contains the buildathon-specific Solidity integration. The main Verigate authorization engine remains a dependency; this is not a fork or rewrite of Verigate.

## Problem

An AI agent can propose a payment, but wallet access must not grant it unrestricted authority. The execution boundary needs to check the exact recipient, amount, destination, expiry and one-time-use status before any destination-side transfer occurs.

## Execution flow

1. Verigate evaluates an `ActionIntent` and issues an Ed25519-signed `ExecutionAuthorization` only for an ALLOW decision.
2. A bridge issuer verifies that artifact off-chain with Verigate's public key, maps its exact action to destination-chain parameters, and calls `VerigateOriginAuthorizationHub.registerAuthorization()` on Base Sepolia.
3. The hub emits `AuthorizationRegistered`. The Reactive contract subscribes to this event and caches the exact commitment on Lasna.
4. The same enabled issuer that registered the authorization calls `requestExecution()` on the origin hub. The hub rejects any other caller before an event is emitted. The event is still only an execution request, not an authorization.
5. Reactive compares the requester identity, recipient, amount, destination chain and destination contract with the cached authorization. It also checks revocation, expiry, replay and the committed hash. The registering issuer address is part of the action commitment.
6. A matching request triggers `requestCallbackV_1_0()` to the Unichain Sepolia receiver. A mismatched request emits `ActionBlocked` on Lasna and makes no destination callback request.
7. The receiver authenticates both the callback proxy and the expected Reactive contract, recomputes the complete issuer-bound action commitment, checks replay and expiry, and transfers its pre-funded native balance to the exact authorized recipient.

The receiver emits `PaymentExecuted` only after the destination-side transfer succeeds. `ActionAllowed` on Lasna means Reactive accepted the request and submitted a callback request; it is not, by itself, proof that the destination payment completed.

## Cryptographic boundary (must remain explicit)

Verigate's current authorization artifact is signed with Ed25519. The EVM contracts in this integration do **not** verify Ed25519 on-chain.

The allowlisted issuer on the origin hub is a bridge attester. Its private key must only be used by an adapter that has first:
- verified the Verigate `ExecutionAuthorization` signature against the configured Verigate issuer public key;
- required `algorithm == "Ed25519"` and a valid, unexpired ALLOW authorization;
- checked `authorization_id`, `action_sha256`, `policy_sha256`, `decision_receipt_sha256`, and the exact action fields;
- checked that the action's network, asset, recipient and exact amount map to the configured destination chain and receiver;
- rejected missing, ambiguous, expired or unsupported fields.

The hub records the Verigate digests in the origin event. The contracts then enforce that exact on-chain commitment across the Reactive callback. This is a deliberate and visible trust boundary, not a claim that Solidity verifies Verigate's Ed25519 signature.

## Demo funding model

`VerigatePaymentReceiver` is a pre-funded testnet execution vault. It transfers native currency held by the receiver contract. This proves the authorization-to-callback-to-side-effect path, but it is not a production non-custodial wallet or an account-abstraction implementation.

Two separate balances are required:
- REACT/lREACT balance for the Reactive contract's event processing and callback requests;
- destination native-token balance on the receiver for callback charges and the test payment.

A callback can fail even after Reactive accepts the request. Confirm the destination `PaymentExecuted` event and transaction, not only `ActionAllowed`.

## Testnet configuration

| Role | Network | Chain ID |
|---|---|---:|
| Origin authorization hub | Base Sepolia | 84532 |
| Reactive contract | Lasna | 5318007 |
| Destination receiver | Unichain Sepolia | 1301 |

Destination callback proxy on Unichain Sepolia:
`0x775c9B990ADe401060B78D0e98684eEf8d2466C1`

Reactive system contract:
`0x8888888888888888888888888888888888888888`

Use testnet-only keys and balances. Never reuse mainnet private keys.

## Build

From this directory, fetch the reviewed Reactive Omni library revision and compile:

```bash
git clone https://github.com/Reactive-Network/reactive-lib-omni.git lib/reactive-lib-omni
git -C lib/reactive-lib-omni checkout 3ade0dcf1d27e67e5783ef807e73a1b9e0c0cce8
forge build
forge test -vv
```

The import remapping is configured in `foundry.toml`. The dependency is intentionally not committed; CI uses the same pinned revision.

## Preparing the origin registration

The bridge preparer accepts the complete JSON response from `POST /v1/actions/authorize` (both `decision_receipt` and `execution_authorization`). It verifies the Ed25519 signatures, checks that the ALLOW receipt and execution authorization describe the same exact action, verifies the receipt digest, checks the target hub's chain/code and the issuer allowlist, then prints a transaction for a wallet to sign. It does not accept or store an EVM private key and does not broadcast.

From the repository root:

```bash
python integrations/reactive-omni/prepare_registration.py authorization-response.json \
  --public-key keys/issuer.pub \
  --origin-hub "$VERIGATE_REACTIVE_ORIGIN_HUB" \
  --issuer "$VERIGATE_REACTIVE_EVM_ISSUER" \
  --destination-receiver "$VERIGATE_REACTIVE_DESTINATION_RECEIVER" \
  --rpc-url "$VERIGATE_REACTIVE_ORIGIN_RPC_URL"
```

The output contains a wallet-signable Base Sepolia transaction. The configured issuer address must already be enabled in the origin hub. The adapter currently supports only `action_type=payment`, `asset=ETH`, network `unichain-sepolia`, an EVM recipient in `action.target`, and exact `amount_exact` decimal values convertible to wei. Change the explicit expected network/asset flags only when the product flow is intentionally configured for another supported mapping.

After the authorization is registered and `AuthorizationCached` is visible on Lasna, the **same issuer wallet** sends the execution request:

```bash
cast send --rpc-url "$BASE_SEPOLIA_RPC_URL" \
  --private-key "$ISSUER_PRIVATE_KEY" \
  "$VERIGATE_REACTIVE_ORIGIN_HUB" \
  "requestExecution(bytes32,address,uint256,uint256,address)" \
  "$AUTHORIZATION_ID" "$RECIPIENT" "$AMOUNT_WEI" 1301 \
  "$VERIGATE_REACTIVE_DESTINATION_RECEIVER"
```

The hub rejects any other caller. The request may still contain a modified recipient or amount so the Reactive contract can emit an explicit `ActionBlocked` record for the negative test.

## Deployment order

A reproducible deployment script is provided. Run it from this directory on a machine with Foundry and funded **testnet-only** wallets:

```bash
export BASE_SEPOLIA_RPC_URL="https://sepolia.base.org"
export LASNA_RPC_URL="https://lasna-rpc.rnk.dev/"
export UNICHAIN_SEPOLIA_RPC_URL="https://sepolia.unichain.org"
export DEPLOYER_PRIVATE_KEY="..."  # testnet deployer/admin only
export ISSUER_PRIVATE_KEY="..."    # Verigate bridge issuer; may be the same wallet

# Optional top-ups, in wei. Set only after checking testnet balances and fee requirements.
export REACTIVE_TOPUP_WEI="..."
export RECEIVER_TOPUP_WEI="..."

bash deploy-testnets.sh
```

The script checks all three chain IDs, pins the official Reactive library revision, deploys the hub → Reactive guard → destination receiver, enables the issuer and configures the callback receiver. It prints contract addresses. Private keys are read from environment variables and are never printed or written to files. Do not paste private keys into chat or commit them.

The Origin Hub must be deployed first because its address is pinned into the Reactive subscription:

1. Deploy `VerigateOriginAuthorizationHub` on Base Sepolia and enable the bridge issuer.
2. Deploy `VerigateReactiveGuard` on Lasna with the Base Sepolia hub address, origin chain ID, destination chain ID and callback gas limit (at least 100,000).
3. Deploy `VerigatePaymentReceiver` on Unichain Sepolia, passing the official Unichain Sepolia callback proxy, the Reactive contract address, Base Sepolia chain ID and origin hub address.
4. Call `setDestinationReceiver()` on the Reactive contract. This is a one-time setter.
5. Fund the Reactive contract with lREACT and the receiver with Unichain Sepolia native currency.
6. Publish a valid Verigate ALLOW authorization. Wait until `AuthorizationCached` is visible on Lasna before requesting execution.
7. Submit one exact request and one modified-recipient or modified-amount request. Verify `PaymentExecuted` for ALLOW and `ActionBlocked` with no destination transfer for BLOCK.

## Status

**SOURCE ONLY — not yet compiled, locally tested, integration-tested or deployed.**

No contract address, transaction hash, callback or live status is claimed by this checkpoint. The next gate is compiling against the official Reactive Omni library, then adding unit tests for action hashing and the ALLOW/BLOCK state transitions before any testnet deployment.
