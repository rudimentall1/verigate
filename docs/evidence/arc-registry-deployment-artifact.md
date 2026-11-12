# Arc Registry deployment artifact provenance

## Deployment identity

- Network: Arc Mainnet, chain ID `5042`
- Contract: `VerigateAuthorityRegistry`
- Address: `0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D`
- Deployment transaction: `0xe85784e81ca0069410e8555961c8403fa02adc1361c7455657106afc96855ebb`
- Deployment block: `30012679`
- Deployer / expected owner and issuer: `0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C`

The transaction is identified as a contract creation in the user-provided Arc Explorer record. The read-only Arc RPC verification run previously retrieved the deployed runtime hash recorded below.

## Recovered build provenance

The historical `integration/arc` ref contains the original Foundry artifact and source used for the deployed Registry:

- Historical source blob: `adf46b928ee82ffc780a7f238272defcfeb73d8b`
- Historical Foundry artifact blob: `11f7a16698f680c4e66f6d37786249f703e63faa`
- Compiler: Solidity `0.8.24+commit.e11b9ed9`
- EVM target: `cancun`
- Optimizer: enabled, 200 runs
- `viaIR`: false
- Metadata bytecode hash: `ipfs`
- Metadata CBOR: enabled
- Source unit: `src/VerigateAuthorityRegistry.sol`

The source snapshot stored beside this document has Keccak-256
`0x117126830a75b649615e382998b63312958e1f7cc64c4c98a356192f8095c684`.
That value exactly matches the source hash embedded in the Solidity artifact metadata.

The preserved runtime is 3,119 bytes and has Keccak-256:

```text
0x6b229c049b9ba0007c318a10759a9827b5a798a4e511611872dcd4cf3973b160
```

This exactly matches the deployed runtime hash returned by the earlier read-only Arc RPC verification run:
[workflow run 43012817343](https://github.com/rudimentall1/verigate/actions/runs/43012817343).

## Why the previous verifier reported a mismatch

The previous verifier compiled the **current** `main` source using the current npm Solidity dependency range (`^0.8.37`) and a source-unit name of `contracts/arc-authority/src/VerigateAuthorityRegistry.sol`. That is not the recovered deployment build.

There are material differences:

1. The deployed source uses `block.timestamp <= auth.validUntil` in `consumeAuthorization`; the current `main` source uses the stricter `block.timestamp < auth.validUntil`.
2. The deployed artifact was compiled with Solidity `0.8.24`; the current npm tooling resolves Solidity `0.8.37`.
3. The deployed metadata source unit is `src/VerigateAuthorityRegistry.sol`, not the current nested path.
4. The deployed Foundry build explicitly targets Cancun. The previous standalone compile script did not explicitly set an EVM target.

Consequently, comparing the current source build byte-for-byte with the immutable historical deployment was the wrong verification target. The mismatch was not evidence that the contract deployment was absent or that the Arc deployment transaction was wrong.

## Correct verification model

The read-only verifier now validates four separate layers:

1. Archived source snapshot hash against the source hash recorded in compiler metadata.
2. Archived runtime bytecode against the runtime hash recorded in the deployment manifest.
3. Deployment transaction, receipt, contract address, deployer and canonical deployment block against Arc Mainnet.
4. Current on-chain runtime, owner, issuer status and finalized head against the reviewed deployment artifact and manifest.

This verifier does not broadcast transactions, deploy contracts, change Registry ownership, or modify any production environment.

## Important semantic boundary

The deployed contract's exact-expiry check is inclusive (`<=`). The current source is stricter (`<`). The archived source is retained only to identify the immutable deployed artifact; it is not the active source tree. Do not claim the deployed contract has the newer strict-expiry behavior unless a separately reviewed migration or redeployment establishes that.

The Registry is an authorization/evidence mechanism, not escrow and not a global wallet firewall. Direct USDC transfers outside the integrated Verigate execution path remain possible.


## Historical Registry activity visible in the executor account

The explorer screenshot also showed three calls from the Registry executor to the deployed contract. The read-only verifier now retrieves each block from Arc Mainnet and checks the full transaction, successful receipt, canonical block hash, Registry-emitted event, event arguments and current stored Registry state.

The verified results are:

| Block | Transaction | Method / event | Result |
|---:|---|---|---|
| 30024727 | `0xa6a2fb23af073085c64bb168f14ee02d90d64fbeb4629dc2724ba1d01624867f` | `registerAuthorization` / `AuthorizationRegistered` | Successful registration. Current state: not consumed, not revoked. |
| 30025935 | `0x5f45d89e0f12e42a0d00268d6125a2b05f6474f4ed786895bc7715cf39ad1696` | `registerAuthorization` / `AuthorizationRegistered` | Successful registration. This authorization is later consumed. |
| 30026205 | `0xc0b2a5de7973da979808ebf5f69e4736ad1eea22fc1fdd5f698b2b44cbad5de8` | `consumeAuthorization` / `AuthorizationConsumed` | Successful one-time consumption of the authorization registered in block 30025935. |

The first authorization ID is `0x3c67a35b4d370c8f80a221270fcfebcf0eba20b6bad478e2761809daab2b7299`.
The second authorization ID is `0xc208b44433c17dbe4e71aea589f5755b1408e37d46a522c1f2022592ed2fdec2`; its intent hash matches between registration and consumption. The state read confirms `consumed=true` and `revoked=false`.

Verification run: [Arc Mainnet read-only run 43160229353](https://github.com/rudimentall1/verigate/actions/runs/43160229353).

This proves successful Registry-level registration and one-time consumption for the observed calls. It does **not** prove that the Verigate API generated the off-chain authorization, and it does not show a subsequent USDC payment or settlement. No payment transaction is attributed to these three Registry calls.
