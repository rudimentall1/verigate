# Arc Mainnet browser wallet adapter

The Arc browser helper is an optional EIP-1193 adapter for interactive wallet demos. It does not hold keys and does not automatically broadcast the final payment. The primary agent path is headless and uses separate issuer and agent signers via `integrations/arc-agent-executor.mjs`.

## Network

- Arc Mainnet chain ID: `5042` (`0x13b2`)
- RPC: `https://rpc.mainnet.arc.io`
- Explorer: `https://explorer.arc.io`
- USDC ERC-20: `0x3600000000000000000000000000000000000000`
- USDC ERC-20 precision: 6 decimals

## Signed authorization request

The caller must construct and sign the action intent before calling the helper.
The `agent_signature` must be produced by the agent identity key using the
same canonical signing procedure as the existing Verigate agent integration.
Do not substitute a wallet signature or an unsigned placeholder.

Required top-level fields follow `ActionAuthorizationRequest`:

- `identity_id`, `capability_id`, `agent_id`
- `agent_signature`, `intent_id`, `timestamp`
- `action_type: "payment"`, `target` (USDC recipient)
- `amount` or `amount_exact`
- `asset: "USDC"`, `network: "arc"`
- `metadata` containing the exact EVM transaction and Arc token binding

The metadata transaction must be generated from the same signed intent:
```js
{
  network_family: "evm",
  evm_transaction: {
    chain_id: 5042,
    from: "<payer-wallet>",
    to: "0x3600000000000000000000000000000000000000",
    value_wei: 0,
    data: "<ERC-20 transfer calldata>"
  },
  arc: {
    chain_id: 5042,
    asset: "USDC",
    token_address: "0x3600000000000000000000000000000000000000",
    token_decimals: 6
  }
}
```

The exact recipient and amount encoded in `data` must match `target` and
`amount_exact`/ `amount`. The agent signature must bind these fields.

## Browser usage

```js
import {
  authorizeArcPayment,
  broadcastAuthorizedArcPayment,
  confirmArcPayment,
} from "./integrations/arc-client.mjs";

const result = await authorizeArcPayment({
  provider: window.ethereum,
  apiBaseUrl: "https://YOUR-VERIGATE-API",
  authorizationRequest: signedActionRequest,
});

// Present recipient, token, amount, and transaction details to the user.
// This is a separate explicit action, after Verigate returned execute=true.
const paymentHash = await broadcastAuthorizedArcPayment({
  provider: window.ethereum,
  walletTransaction: result.wallet_transaction,
});

// Verify the mined payment against the original authorization and finalized Arc state.
const settlement = await confirmArcPayment({
  provider: window.ethereum,
  apiBaseUrl: "https://YOUR-VERIGATE-API",
  authorization: result.authorization,
  registration_tx_hash: result.registration_tx_hash,
  consume_tx_hash: result.consume_tx_hash,
  payment_tx_hash: paymentHash,
});

console.log(settlement.payment_settlement);
```

## Transaction order

1. Client checks Arc Mainnet and the wallet account for the registry executor.
2. Client asks Verigate to authorize the signed payment intent.
3. Executor wallet signs and broadcasts the registry registration transaction.
4. Client waits for a successful receipt and asks Verigate to verify it.
5. Executor wallet signs and broadcasts the registry consumption transaction.
6. Client waits for a successful receipt and asks Verigate to verify it.
7. Verigate verifies the canonical Arc evidence and consumes the local one-time authorization.
8. Only if `execute === true`, the helper returns the payment transaction.
9. The application explicitly calls `broadcastAuthorizedArcPayment` after
   presenting the payment to the user.
10. After the payment is mined, the application calls `confirmArcPayment`.
    Verigate returns settlement evidence only after checking the exact USDC
    Transfer event and finalized canonical block.

The registry executor and the payment sender are not assumed to be the same
account. Each wallet operation checks that the connected provider exposes the
account specified in that transaction's `from` field.

## Failure behavior

The helper stops on a wrong chain, unavailable account, reverted transaction,
receipt timeout, non-2xx API response, failed registration/consumption
confirmation, or `execute !== true`. It never broadcasts the payment in the
authorization call. `confirmArcPayment` also fails if the payment receipt is
not yet available or Verigate cannot verify finalized settlement.

The helper currently expects the caller to provide an EIP-1193 provider and a
fully signed `ActionAuthorizationRequest`. Agent-intent signing and UI review
remain the responsibility of the integrating application.
