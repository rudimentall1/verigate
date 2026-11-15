# Reactive Omni Buildathon — Technical Checkpoint

**Branch:** `hackathon/reactive-omni-buildathon`  
**Track:** Set It and Forget It  
**Checkpoint date:** 2026-11-15

## Confirmed from Verigate source

- `attest/receipt.py` defines `ExecutionAuthorization` as a separate, short-lived capability.
- It is signed with Ed25519; canonical JSON serialization is sorted-key, compact JSON.
- Its payload includes `authorization_id`, `decision_receipt_sha256`, `policy_sha256`, `intent_id`, `agent_id`, `action`, `action_sha256`, `issued_at`, `expires_at`, and additional capability/authority bindings.
- `action_sha256` is SHA-256 over canonical JSON for the exact normalized action.
- ALLOW execution authorization requires capability, dynamic authority and policy binding.
- `api/main.py` exposes `POST /v1/actions/authorize`, returning a decision receipt and an execution authorization when permitted.
- Existing `contracts/VerigateAtomicStateGuard.sol` explicitly documents that it does not independently verify a per-action signed authorization on-chain. It must not be presented as the Reactive integration.

## Reactive integration created in this branch

- `src/VerigateOriginAuthorizationHub.sol`: issuer-gated origin event publisher, one-time authorization IDs, revocation, destination-bound commitment and public execution-request event.
- `src/VerigateReactiveGuard.sol`: Reactive Omni subscriptions, authorization cache, exact action comparison, expiry/revocation/replay checks, explicit BLOCK evidence, typed callback request.
- `src/VerigatePaymentReceiver.sol`: callback proxy + Reactive sender authentication, commitment recomputation, one-time payment and destination-side execution evidence.
- `foundry.toml` and integration README document dependency setup, network parameters, deployment order and threat boundary.

## Important trust and product boundaries

1. Verigate uses Ed25519. EVM contracts here do not verify Ed25519 signatures.
2. The origin hub's allowlisted issuer is a bridge attester. It must verify Verigate's signed execution authorization off-chain before publishing a commitment.
3. The action hash binds origin chain and hub, authorization ID, Verigate action/policy/receipt digests, destination chain and receiver, recipient, exact wei amount and expiry.
4. The destination receiver is a pre-funded testnet executor. This proves a real bounded side effect, but is not a production non-custodial wallet.
5. `ActionAllowed` only proves Reactive accepted the request and submitted the callback request. The destination `PaymentExecuted` event and transaction are required to claim successful execution.
6. An invalid request must produce `ActionBlocked` on Lasna and no destination payment.

## Verification status

| Item | Status |
|---|---|
| Verigate authorization payload source review | SOURCE REVIEWED |
| Reactive Omni API/library interface review | SOURCE REVIEWED |
| New Solidity contracts | SOURCE ONLY |
| Solidity compilation | NOT RUN |
| Unit tests | NOT RUN |
| Testnet deployment | NOT DEPLOYED |
| End-to-end callback | NOT TESTED |
| Independent verification | NOT VERIFIED |

## Next steps

1. Compile all three contracts against a pinned revision of `Reactive-Network/reactive-lib-omni`.
2. Add tests for exact hash parity across origin/reactive/destination, unauthorized issuer, duplicate ID, expired/revoked/consumed authorization, recipient mismatch and amount mismatch.
3. Build the adapter that verifies the Verigate Ed25519 artifact and submits the issuer transaction.
4. Deploy Base Sepolia → Lasna → Unichain Sepolia, then collect real transaction hashes and callback evidence.
