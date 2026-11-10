# Verigate Authority Registry — Arc Mainnet Deployment

## Deployment

- Project: Verigate
- Contract: VerigateAuthorityRegistry
- Network: Arc Mainnet
- Chain ID: 5042
- Deployer: 0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C
- Owner: 0x1429906b663608DB6aDeAb8F975B47aFbbe8c68C
- Contract address: 0x4D09CdD490c1Ce48BCB6dA5c1A6Bf41E2f5e853D
- Deployment transaction: 0xe85784e81ca0069410e8555961c8403fa02adc1361c7455657106afc96855ebb
- Block: 30012679
- Receipt status: 1 (success)
- Gas used: 774955
- Solidity: 0.8.24

## On-chain verification

- Contract bytecode confirmed at deployed address.
- owner() returns the deployer address.
- Constructor emitted IssuerUpdated for the deployer with enabled=true.

## Contract capabilities

- Issuer management.
- Authorization registration.
- Executor-bound, one-time authorization consumption.
- Expiration checks.
- Authorization revocation.

## Scope

This is Verigate's own Authority Registry deployment.
It is distinct from Agentic Wallet Guardian v3 and from the Arc USDC token contract.

The registry complements Verigate's off-chain signed authorization and policy engine.
