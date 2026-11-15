# Reactive Omni Buildathon — Technical Checkpoint

**Branch:** `reactive-omni-buildathon`  
**Track:** Set It and Forget It  
**Checkpoint:** 2026-11-15

## Executive state

The integration is implemented and the three-chain testnet setup has been exercised far enough to register a real Verigate authorization and submit its execution request on Base Sepolia.

The final destination-side payment is **not confirmed**. No submission text should claim that the full cross-chain payment succeeded until the Unichain transaction and `PaymentExecuted` event are verified.

## Live deployment evidence

| Component | Network | Address / transaction | Evidence |
|---|---|---|---|
| Origin Authorization Hub | Base Sepolia (84532) | `0x05d23191f063D704A3D2e367D5C268f1B5834637` | Deployment tx `0xd955ae00dabb4b9bf2b5809c136c643c37847f0bb41fb225e503fa733c60bf58`, block `0x3859904` |
| Reactive Guard | Lasna (5318007) | `0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D` | Deployment tx `0x81d496664ae8c12a91393b380eaa13683fde815214942e9021a34fa56848f2c4`, block `8402135` (hex `0x8034d7`), receipt status 1 |
| Payment Receiver | Unichain Sepolia (1301) | `0xF1C8af8dA8c0cFe23ad04ca73533EF0AdE1B85B4` | Deployment tx `0x3eb8d65c96ed88535386177102c6619aead08b79ab5394eb6073e93b2bcea9cd`, block `0x40bdf16` |
| Unichain callback proxy | Unichain Sepolia | `0x775c9B990ADe401060B78D0e98684eEf8d2466C1` | Configured callback endpoint |

The hub issuer is enabled. The Guard was configured with the origin hub and destination receiver. The Receiver was deployed with the origin hub and expected Reactive sender. The callback proxy and service-provider configuration were read from the deployed receiver.

**Verified Guard deployment:** receipt retrieved from Lasna RPC `https://lasna-rpc.rnk.dev/` (chain ID `5318007`). The receipt reports `contractAddress` `0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D`, block `8402135` (`0x8034d7`), status `1 (success)`. The earlier malformed/truncated candidate has been replaced with this receipt-confirmed address.

## Successful origin-chain execution

A fresh Verigate ALLOW artifact was generated and validated by `integrations/reactive-omni/prepare_registration.py`.

| Field | Value |
|---|---|
| Agent | `reactive-omni-payment-agent` |
| Identity ID | `bea1705fe3db7b27dfe4f09be1caeed784d89ce4ff4745949cd7fc4892d357f6` |
| Capability ID | `reactive-omni-unichain-eth-payment-v2` |
| Recipient | `0x4c07B4f328FA738290Db96BCE2F9CBc4d020D2CB` |
| Amount | `0.0001 ETH` (`100000000000000 wei`) |
| Destination | Unichain Sepolia, chain ID 1301 |
| Receiver | `0xF1C8af8dA8c0cFe23ad04ca73533EF0AdE1B85B4` |
| Policy digest | `c957fee50afe22ba2f26495729e1831be57af858b9ceb68c2d58c06dc26912fe` |
| Authorization ID | `0x88460c852f7ba61c5ce29e0f0c689948dba0f3f9096e3804eed959e8d32753d8` |
| Action hash | `0x4ef54c502856df6bc92df12391ed8fca43208a0d7ba846d04e470a8b7965c789` |
| Decision receipt hash | `0xcc9ddd7e660f87b5f623214789b1fa451f20dd0364eb5b27de814e1a6d05660a` |

Origin transactions:

- `registerAuthorization`: `0xded94bd71d829c91bc914acef6e62f0dfbc99dcf2e08084115e9026ce8bc3a97` — Base Sepolia, block 59122735, status 1.
- `requestExecution`: `0x1b4b855d1229c27ca725371c9be3b54e98b95ada13ac0eaa36f7caf2760685b9` — Base Sepolia, block 59123139, status 1.

Both transactions emitted the expected origin events with the authorization ID, recipient, issuer, amount, destination chain and receiver.

## Destination outcome: not yet proven

A query of the latest 1,000 Unichain Sepolia blocks returned no `PaymentExecuted` event at the time of that check. This is not proof that no callback can ever arrive; it means the required destination evidence has not been obtained.

The receiver's last recorded balance was zero. Callback proxy reserve/debt values were also last read as zero. Funding the receiver or callback proxy is a separate on-chain spend and has **not** been authorized as part of this checkpoint.

Do not treat any of the following as payment proof:

- successful origin `registerAuthorization`;
- successful origin `requestExecution`;
- a Reactive `ActionAllowed` event;
- a callback request without a successful destination receipt.

The proof required to close the loop is a successful Unichain Sepolia transaction to the receiver, the matching `PaymentExecuted` event, and a recipient balance increase of exactly 0.0001 ETH (net of no receiver-side deductions; gas is paid by the callback path).

## Product and security boundaries

1. Verigate evaluates the action and issues a signed ALLOW authorization. The model/agent does not make the ALLOW/WARN/BLOCK decision.
2. Verigate signs its authorization with Ed25519. The EVM contracts do not verify Ed25519 on-chain.
3. The allowlisted EVM issuer is a bridge attester. The bridge preparer verifies the receipt and execution authorization before preparing the origin transaction. The issuer key is a separate trust boundary.
4. The commitment binds the origin chain and hub, issuer, authorization ID, Verigate action/policy/receipt digests, destination chain and receiver, recipient, exact amount and expiry.
5. Reactive independently checks the cached authorization, issuer, exact requested fields, expiry, revocation and replay before requesting the callback.
6. The receiver authenticates both the callback service provider and expected Reactive sender, recomputes the commitment, enforces expiry/replay, and transfers only the exact amount.
7. The receiver is a pre-funded testnet executor, not a production non-custodial wallet.

## Tests and CI checkpoint

- Solidity: 15 Foundry tests passed locally, 0 failed, 0 skipped, across 3 suites.
- Python bridge preparer: test suite covers exact wei conversion, rejects float/over-precision amounts, and checks registration ABI encoding.
- GitHub Actions runs previously reported green for the Reactive integration: Solidity build/tests and Python bridge checks. CI run IDs recorded in the working checkpoint: `43697492511` and `43697492541`.
- Do not describe the 15-test local suite as a CI result unless a CI run for the exact current branch commit confirms it.
- Compiler/lint warnings remain for review.

## Remaining gates before submission

1. Verify the Reactive-side authorization cache and request handling for this authorization.
2. Resolve callback funding requirements. Ask before sending any funds to the receiver or callback proxy.
3. Obtain the destination `PaymentExecuted` transaction and verify the recipient balance change.
4. Run a negative test with a changed recipient or amount from the registered issuer; capture `ActionBlocked` on Lasna and prove no destination payment occurred.
5. Run CI against the exact final branch head and review compiler warnings.
6. Record exact explorer links, demo steps, and measured end-to-end latency only after the evidence exists.

## Submission rule

Until gates 1–6 are closed, describe the project as a deployed testnet integration with successful origin authorization/request transactions and a pending destination callback/payment proof. Do not claim a completed cross-chain transfer, a measured full-loop latency, or a verified negative-path demo.
