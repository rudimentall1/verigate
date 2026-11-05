# Anna 0.1.12 / Executa 0.1.11 — connected-wallet execution

## Scope

This release adds a connected-wallet submission path for native USDC on Base and Ethereum.
It does not enable Solana wallet submission.

## Flow

1. Anna AI interprets the request; Verigate's deterministic policy owns ALLOW/WARN/BLOCK.
2. The user explicitly requests a one-time permission.
3. Executa constructs canonical ERC-20 transfer(address,uint256) calldata using the exact payee and amount (USDC: 6 decimals) and includes the EVM transaction envelope in the signed action.
4. The UI verifies the Ed25519 Decision Receipt and Execution Authorization.
5. The user selects Send with connected wallet. The app checks an injected EIP-1193 provider, active chain and wallet account.
6. The Executa passes the authorization into ExecutionRouter.consume. The router verifies the signature, adapter, signed execution artifact, state checks and single-use nonce.
7. Only after successful consumption does the UI pass the exact adapter-returned transaction envelope to eth_sendTransaction.
8. The wallet displays its signing confirmation, signs and broadcasts. Anna/Verigate never access the wallet private key.

## Supported network mapping

| Network | Chain ID | Native USDC contract |
|---|---:|---|
| Ethereum | 1 | 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 |
| Base | 8453 | 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 |

Addresses are based on Circle's native USDC network listings. USDC uses 6 decimals.

## Important execution semantics

- The authorization is not itself a transaction.
- Router consumption happens before the wallet's send request. If the wallet rejects/cancels or the send call fails, the authorization remains consumed; a fresh authorization is required.
- The app submits via the wallet provider after router consumption. It does not use a server-side private key or store wallet secrets.
- A returned transaction hash is reported as SUBMITTED, not CONFIRMED.
- The application does not currently support Solana transaction construction/signing/submission. Solana policy checks and authorization remain separate from wallet execution.
- The wallet provider must be injected into the Anna app browsing context. If no EIP-1193 provider is present, the app fails closed and does not consume the permission.

## Validation required

- Full Python repository tests.
- Anna UI jsdom end-to-end tests with a mocked EIP-1193 wallet.
- Strict Anna app manifest validation.
- Windows Executa binary rebuild and smoke test.
- Fresh-install test in Anna Cloud Agent with a wallet on Base and Ethereum; no real-funds test is required to validate the UI and router gate. Any optional live send must be explicitly approved by the user and use a small amount.
