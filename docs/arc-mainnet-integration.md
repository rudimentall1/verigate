# Arc Mainnet integration

Verigate includes a first-party Arc mainnet payment adapter. It reuses the
same Arc mainnet parameters and non-custodial wallet-signing model proven in
the Agentic Wallet Guardian v3 Arc demo, but routes authorization through
Verigate's own signed ActionIntent, capability and execution-consumption
protocol.

## Network configuration

- Network: Arc mainnet
- Chain ID: `5042`
- RPC: `https://rpc.mainnet.arc.io` (override with `VERIGATE_ARC_RPC_URL`)
- Explorer: `https://explorer.arc.io`
- Canonical USDC ERC-20: `0x3600000000000000000000000000000000000000`
- USDC ERC-20 transfer decimals: `6`
- Native Arc gas asset: USDC, `18` decimals

**Do not mix the two USDC denominations.** ERC-20 `transfer(address,uint256)`
uses 6 decimals. Arc's native gas/value denomination uses 18 decimals. An
ERC-20 transfer therefore sets transaction `value_wei=0`; the payment amount
is encoded in the token calldata.

## Endpoints

### Read-only network check

```http
GET /v1/integrations/arc/status
```

The endpoint verifies the live RPC chain ID, reads the latest block and gas
price, checks that the canonical USDC contract has bytecode, and calls
`decimals()` to confirm the ERC-20 interface returns 6.

### Signed Arc payment authorization

```http
POST /v1/integrations/arc/authorize
Content-Type: application/json
```

This endpoint accepts the same signed identity/capability request as
`POST /v1/actions/authorize`, but requires an Arc USDC payment intent and
validates the exact EVM transaction envelope before Verigate issues authority.
The request's `metadata.evm_transaction` must bind chain ID, sender, token
contract, zero native value and the exact ERC-20 recipient/amount calldata.

A client can construct that metadata with:

```python
from integrations.arc import arc_payment_metadata

metadata = arc_payment_metadata(
    sender="0x1111111111111111111111111111111111111111",
    recipient="0x2222222222222222222222222222222222222222",
    amount="1.25",
)
```

The agent must sign the complete normalized ActionIntent, including this
metadata. Verigate verifies that signature, checks the registered identity
and capability, then evaluates the configured policy. The response includes
a wallet-signable transaction only when an executable authorization exists.

### Execution order

1. Obtain the signed Arc authorization from
   `POST /v1/integrations/arc/authorize`.
2. Submit that exact `execution_authorization` to
   `POST /v1/execution/consume`.
3. Continue only when the response is `execute=true`.
4. Ask the connected wallet to sign and broadcast the exact returned
   `wallet_transaction` on chain ID 5042.
5. Independently verify the transaction receipt against Arc mainnet.

The wallet remains the signer. Verigate does not store user wallet keys and
does not custody USDC. The API-side consume step is a pre-broadcast application
boundary; this integration does not claim that an arbitrary wallet or direct
RPC caller is prevented from bypassing the client flow. Stronger on-chain
enforcement requires a deployed account/guard integration.

## Verification and tests

Run the offline unit tests:

```bash
PYTHONPATH=. python3 -m unittest tests.test_arc_integration -v
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

The tests use a deterministic mock JSON-RPC transport. They do not send
mainnet transactions or claim a production deployment.
