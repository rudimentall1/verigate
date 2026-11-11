# Verigate Arc Mainnet integration

Verigate's Arc integration combines a signed agent payment intent, identity and
capability checks, deterministic policy evaluation, an on-chain one-time
authority registry, and an explicit non-custodial wallet handoff.

This guide describes the **Arc Authority Registry flow**. The older generic
`POST /v1/execution/consume` flow is not valid for Arc authorizations: the API
returns HTTP 409 for Arc on that endpoint to prevent bypassing the registry
confirmation sequence.

## Network configuration

- Network: Arc Mainnet
- Chain ID: `5042` (`0x13b2`)
- RPC: `https://rpc.mainnet.arc.io` (override with `VERIGATE_ARC_RPC_URL`)
- Explorer: `https://explorer.arc.io`
- Canonical USDC ERC-20: `0x3600000000000000000000000000000000000000`
- USDC ERC-20 transfer decimals: `6`
- Native Arc gas asset: USDC, `18` decimals

Do not mix the two denominations. ERC-20 `transfer(address,uint256)` uses
6 decimals. Native transaction value uses Arc's 18-decimal gas denomination.
An ERC-20 payment therefore sets `value_wei=0`; the amount is encoded in token
calldata.

## Agent onboarding and signed intent

The framework-independent Python SDK is documented in
[`docs/AGENT_SDK_ARC.md`](AGENT_SDK_ARC.md).

1. The agent creates and retains its own Ed25519 private key. The SDK creates
   key files with owner-only permissions and rejects unsafe existing modes.
2. The agent creates a public enrollment package containing its public key,
   agent ID, capability ID, allowed recipients, amount limit and expiry.
3. An operator transfers that package to the Verigate API host and runs
   `python scripts/enroll_agent_arc.py --package arc-enrollment.json`.
   Enrollment is operator-controlled; there is no public self-registration
   endpoint.
4. The agent signs an exact Arc USDC ActionIntent. The signature binds the
   sender, recipient, amount, Arc chain, canonical token and ERC-20 calldata.

## API endpoints

### Network and token status

`GET /v1/integrations/arc/status`

Checks the live RPC chain ID, latest block and gas price, canonical USDC
contract bytecode, and `decimals()` value of 6.

### Authorization

`POST /v1/integrations/arc/authorize`

The API validates the Arc payment fields and exact EVM transaction envelope,
checks the live Arc network/token metadata, verifies the agent identity and
signature, checks the registered capability and policy, and issues a signed
Decision Receipt and short-lived Execution Authorization when allowed.

The response includes the configured Registry address and the wallet-signable
registration transaction. It deliberately returns
`wallet_transaction: null` at this stage.

### Registration confirmation

`POST /v1/integrations/arc/registration/confirm`

The executor wallet submits the registration transaction. Verigate then
checks the transaction hash, chain ID, sender, destination, calldata, zero
native value, successful receipt, inclusion block number and hash, the Arc
finalized block tag, block timestamp, expected Registry event, and stored
Registry state. The timestamp must fall within the signed authorization
validity interval. The receipt block must be at or below the RPC's finalized
head; if the RPC cannot provide a valid finalized block, confirmation fails closed.

Only after those checks does the API return the Registry consumption
transaction.

### Consumption confirmation

`POST /v1/integrations/arc/consume/confirm`

The executor wallet submits the consumption transaction. Verigate repeats
the transaction and canonical block checks, verifies the consumption event
and stored state, then consumes the local one-time execution nonce using the
verified Arc block timestamp.

Only when all checks succeed does the API return the exact wallet payment
transaction and Arc authority evidence.

### Generic consume route

`POST /v1/execution/consume`

Arc authorizations are explicitly rejected with HTTP 409. This route cannot
be used to skip Registry registration and consumption.

## Wallet client transaction sequence

The EIP-1193 helper is documented in
[`docs/ARC_WALLET_CLIENT.md`](ARC_WALLET_CLIENT.md).

1. Check the connected wallet is on Arc Mainnet.
2. Request authorization from Verigate.
3. Check that the connected wallet exposes the configured Registry executor
   account, then sign and broadcast the registration transaction.
4. Wait for a successful receipt and ask Verigate to confirm registration.
5. Sign and broadcast the returned Registry consumption transaction.
6. Wait for a successful receipt and ask Verigate to confirm consumption.
7. Receive the exact authorized payment transaction only after
   `execute === true`.
8. Present the payment details and call
   `broadcastAuthorizedArcPayment` only as a separate, explicit wallet
   action.

The Registry executor and payment sender may be different accounts. The
client checks the account required by each transaction.

## Security boundary and limitations

- Verigate does not custody the agent key or payment wallet key.
- The Registry stores an authorization ID, an intent hash, executor, expiry
  and one-time consumed/revoked state. The hash commits to the signed
  authorization envelope; the contract does not store the complete payment
  payload.
- Registration is issuer-gated. Consumption is executor-gated, bound to the
  stored intent hash, one-time and expiry-checked. Revocation is supported.
- The API releases the payment transaction only after both on-chain Registry
  operations are confirmed and the local execution nonce is consumed.
- The Registry is an authority/evidence mechanism, **not an escrow contract
  or a USDC transfer guard**. A wallet owner or external caller can still
  submit a direct USDC transfer outside this client flow. Do not describe this
  version as technically preventing all out-of-band wallet transfers.
- Receipt verification compares the receipt block hash with the RPC's
  canonical block and requires the inclusion block to be at or below Arc's
  finalized block tag. Arc uses deterministic finality; Verigate does not add
  an arbitrary confirmation-depth delay.
- RPC-based verification depends on the configured Arc RPC returning honest,
  consistent chain data. The API also requires VERIGATE_ARC_REGISTRY_CODE_HASH
  and rejects a runtime bytecode hash mismatch. Obtain the reviewed hash with
  `npm run verify:arc-deployment`; do not configure it until the script's
  compiled/deployed bytecode comparison and owner/issuer checks have been
  independently reviewed. Independent evidence should retain transaction
  hashes, block references, contract address and deployed bytecode/source
  identity.

## Tests and evidence

Relevant automated coverage:

- `tests/test_arc_api.py`: Arc status, signed authorization, generic-consume
  bypass rejection, registration and consumption API flow.
- `tests/test_arc_authority_registry.py`: deployment checks, transaction
  construction, transaction/receipt binding, event and Registry-state
  validation, canonical block hash, finalized-head and trusted timestamp/expiry behavior,
runtime bytecode hash pinning and enabled issuer checks.
- `tests/test_arc_agent_enrollment.py` and
  `tests/test_agent_sdk_arc_api.py`: operator enrollment and SDK-to-API flow.
- `tests/arc-client.test.mjs`: wallet chain/account checks, registration and
  consumption sequence, explicit payment broadcast, and fail-closed behavior.
- `tests/agent-sdk-arc-client.test.mjs`: Python SDK to JavaScript wallet-client
  cross-language path.

Run focused tests:

```bash
PYTHONPATH=. python3 -m unittest tests.test_arc_api tests.test_arc_authority_registry tests.test_arc_agent_enrollment tests.test_agent_sdk_arc_api -v
npm run test:arc-client
node --test tests/agent-sdk-arc-client.test.mjs
npm run compile:arc-authority
```

These tests use fixtures/mocks for the Arc RPC and wallet provider. They prove
the tested software paths, not a live Verigate-authorized mainnet payment.

For grant submissions, distinguish the team's earlier live Arc transaction
from the separate Verigate Registry deployment and from a Verigate-authorized
payment. Record each transaction hash and its project attribution accurately.
