# PortalDot V3: build checklist and current state

**Updated:** 2026-10-14  
**Build repository:** [rudimentall1/verigate-portaldot](https://github.com/rudimentall1/verigate-portaldot)  
**Latest implementation commit:** [6c59a74](https://github.com/rudimentall1/verigate-portaldot/commit/6c59a74f75fa2f01e72d45b1a193d71f60e22dfa)

## Current status

The repository is public. It contains a Solidity native-payment guard, Hardhat tests, an RPC preflight, a deployment script, a Verigate bridge-signing CLI, and security notes.

GitHub Actions compiled the contract and passed 15 tests on the bridge commit. The developer has since run the same checks locally on Windows: `npm test` reported 15 passing and `npm run compile` returned `Nothing to compile`.

Still unverified:
- public PortalDot V3 RPC and current block (the latest local preflight returned `fetch failed`);
- wallet H160-to-SS58 mapping and faucet funding;
- CLI run against a real response from the Verigate API;
- any deployment or transaction on PortalDot V3.

The event team reported the public V3 RPC was not working. Do not use a guessed replacement endpoint or claim deployment success.

## Run from a local checkout

```bash
git clone git@github.com:rudimentall1/verigate-portaldot.git
cd verigate-portaldot
npm install
npm test
npm run compile
```

The repository's GitHub Actions run is at:
https://github.com/rudimentall1/verigate-portaldot/actions/runs/38517207580

## Network gate

Copy .env.example to .env, then run:

```bash
npm run preflight
```

The script requests eth_chainId and eth_blockNumber from the official V3 EVM RPC and fails closed if it cannot connect or the returned chain ID differs from 420420777. A successful RPC preflight is required before deploying.

After the EVM deployer is generated, use the official PortalDot V3 guide's Developer → Runtime calls → reviveApi → accountId step to confirm the mapped SS58 account before funding it. Do not assume a 0x EVM address and a 5... SS58 address are interchangeable.

Official guide:
https://github.com/ItsCogumellum/portaldot-v3-testnet-guide

## Current contract scope

PortalDotAgentGuard accepts only a signed native-token transfer. Its EIP-712 authorization binds the recipient, raw EVM base-unit amount, nonce, deadline, action ID, chain ID and verifying contract. It does not expose a caller-selected arbitrary call.

The bridge signing CLI accepts a saved response from Verigate POST /v1/actions/authorize. Its signed action must use:
- action_type: portaldot.native_transfer
- target: destination EVM address
- network: portaldot-v3
- asset: tPOTv3
- amount_exact: positive integer string of EVM transfer base units
- metadata.portaldot_v3: matching chain_id, recipient and amount_base_units

It asks the configured Verigate POST /v1/verify endpoint to validate the Ed25519 decision receipt and execution authorization, then signs a short-lived EIP-712 payload. It does not broadcast a transaction. Confirm PortalDot's actual EVM denomination before showing amounts in human-readable POT.

## Next steps

1. [x] Run install, test and compile on the local checkout. `npm test`: 15 passing; `npm run compile`: `Nothing to compile`.
2. [ ] Re-check the public RPC with `npm run preflight` later. The current result is `fetch failed`; keep building but do not deploy.
3. Capture a real ALLOW and BLOCK response from the running Verigate instance; run the bridge against both and confirm BLOCK never produces a signature.
4. Add/review tests for amount, target, action ID, expiry, nonce and wrong-chain behavior.
5. Once RPC is back, map the EVM deployer to SS58, request test tPOT, deploy and record the actual transaction receipt.
6. Add reproducible demo instructions and evidence only after independently checking PortalDot state.

## Security constraints

- Never commit .env, seed phrases, deployer keys, bridge keys or Verigate keys.
- Use separate deployer and bridge-signing keys, both disposable and testnet-only.
- Keep the funded contract balance small.
- The bridge signer is a trust boundary. Solidity verifies EIP-712 secp256k1 signatures, not Verigate's Ed25519 signature.
- No deployment address, transaction hash or explorer screenshot is valid evidence unless confirmed on the live expected chain.


## Check the real Verigate-to-bridge path

The developer has confirmed the local API at `http://127.0.0.1:8000` returns `status=ok` and its OpenAPI includes `/v1/actions/authorize`, `/v1/verify` and `/v1/verify/adversarial`.

Run the isolated harness from the PortalDot repository using the Python interpreter in the local Verigate checkout:

```powershell
$verigateRoot = "$env:USERPROFILE\\Desktop\\Work\\verigate\\verigate"
& "$verigateRoot\\.venv\\Scripts\\python.exe" ".\\scripts\\verigate_local_demo.py" --verigate-root "$verigateRoot"
```

It starts a temporary verifier on port 8001 with separate test keys and database, then checks ALLOW, BLOCK, signed artifact verification, and the bridge CLI against a dummy contract domain. It cleans the temporary private keys/database afterwards. This is a local integration check only; it makes no PortalDot transaction.

Do not proceed to live signing or deployment unless the harness prints PASS. If it fails, keep the full traceback/output and fix the failing boundary before continuing.
