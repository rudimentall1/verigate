# Reactive Omni Buildathon — Technical Checkpoint

**Branch:** `reactive-omni-buildathon`  
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

- `src/VerigateOriginAuthorizationHub.sol`: issuer-gated origin event publisher, one-time authorization IDs, revocation, destination-bound commitment, and execution requests restricted to the same enabled issuer that registered the authorization.
- `src/VerigateReactiveGuard.sol`: Reactive Omni subscriptions, authorization cache, exact action and issuer comparison, expiry/revocation/replay checks, explicit BLOCK evidence, typed callback request.
- `src/VerigatePaymentReceiver.sol`: callback proxy + Reactive sender authentication, issuer-bound commitment recomputation, one-time payment and destination-side execution evidence.
- `prepare_registration.py`: validates the signed ALLOW receipt and execution authorization, checks that both describe the same action, verifies receipt-to-authorization digest binding, checks the Base Sepolia hub and enabled issuer, and prepares a wallet-signable registration transaction without accepting an EVM private key.
- `tests/test_prepare_registration.py`: covers exact wei conversion, rejects float/over-precision amounts, and checks all nine ABI arguments in the registration transaction.
- `foundry.toml`, integration README and `.github/workflows/reactive-omni.yml` document the pinned Reactive library dependency, network parameters, deployment order, threat boundary and compile gate.

## Important trust and product boundaries

1. Verigate uses Ed25519. EVM contracts here do not verify Ed25519 signatures.
2. The origin hub's allowlisted issuer is a bridge attester. It must verify Verigate's signed execution authorization off-chain before publishing a commitment.
3. The action hash binds origin chain and hub, the EVM issuer that registered the authorization, authorization ID, Verigate action/policy/receipt digests, destination chain and receiver, recipient, exact wei amount and expiry.
4. The destination receiver is a pre-funded testnet executor. This proves a real bounded side effect, but is not a production non-custodial wallet.
5. `ActionAllowed` only proves Reactive accepted the request and submitted the callback request. The destination `PaymentExecuted` event and transaction are required to claim successful execution.
6. The origin hub accepts execution requests only from the same enabled issuer that registered the authorization; Reactive independently checks the issuer in the observed event. Other callers revert at origin and cannot consume the authorization.
7. A modified request submitted by the registered issuer must produce `ActionBlocked` on Lasna and no destination payment.

## Verification status

| Item | Status |
|---|---|
| Verigate authorization payload source review | SOURCE REVIEWED |
| Reactive Omni API/library interface review | SOURCE REVIEWED |
| New Solidity contracts | SOURCE ONLY |
| Solidity compilation | PASS in GitHub Actions using pinned Reactive library commit `3ade0dcf1d27e67e5783ef807e73a1b9e0c0cce8`; compiler warnings remain |
| Foundry unit tests | PASS: 11 passed, 0 failed across 3 suites in GitHub Actions |
| Python bridge adapter tests | PASS: 4 passed in GitHub Actions |\n| Testnet deployment | NOT DEPLOYED |
| End-to-end callback | NOT TESTED |
| Independent verification | NOT VERIFIED |

## Next steps

1. Preserve the green GitHub Actions build and test result against pinned Reactive library commit `3ade0dcf1d27e67e5783ef807e73a1b9e0c0cce8`; review and address compiler warnings before deployment.
2. Add tests for exact hash parity across origin/reactive/destination, unauthorized issuer, duplicate ID, expired/revoked/consumed authorization, recipient mismatch and amount mismatch.
3. Exercise the bridge preparer against a real Verigate authorization artifact and a deployed hub; have the configured EVM issuer sign and submit the prepared transaction.
4. Deploy Base Sepolia → Lasna → Unichain Sepolia, then collect real transaction hashes and callback evidence.
