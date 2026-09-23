# Verigate — Stack

## Runtime

- Python 3
- Core: standard library plus cryptography and PyYAML
- API: FastAPI + Pydantic + Uvicorn
- Persistence: SQLite through the Storage abstraction
- Tests: Python unittest discovery

## Core

- `core.models`: PaymentIntent, ActionIntent, AgentIdentity, Capability and decisions
- `core.policy` + `core.rules`: deterministic policy evaluation
- `core.identity`: cryptographic identity registry and agent-signed intent verification
- `core.authorization`: portable execution authorization
- `core.capabilities`: active authority registry and revocation
- `core.engine`: orchestration and identity/capability-bound authorization paths
- `core.storage`: audit/rate/spend state plus identity and capability registries

## Evidence and authorization

- Ed25519 signing and independent verification
- DecisionReceipt for signed decision evidence
- ExecutionAuthorization for short-lived, nonce-bound execution authority

## Enforcement

- Chain-independent ExecutionAdapter protocol
- Local fail-closed adapter
- Dependency-light EVM adapter and RPC path
- Solana execution adapter and RPC path
- Execution receipts and confirmation monitoring

## Integrations

- x402 payment parser
- CoinMarketCap RWA adapter under `adapters/cmc`
- Hackathon-specific material under `hackathons/`

## Testing convention

Prefer tests at the highest practical seam and assert observable security behavior: authorization issuance, rejection, replay protection, tamper rejection, broadcast count, confirmation, and evidence.

## Commands

Full suite:
`PYTHONPATH=. python3 -m unittest discover -s tests -v`

API:
`uvicorn api.main:app --reload`
