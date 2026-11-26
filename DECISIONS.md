# Architecture and engineering decisions

## Arc is one network integration

Arc-related implementation is consolidated into one integration branch. Keep network-specific code under the existing Arc integration/contracts/deploy/scripts/tests seams; do not fork the product into separate Arc variants.

## Trust boundaries

- Verigate API authorizes and verifies; it does not hold EVM issuer or agent private keys.
- Operator issuer and agent executor are separate roles with separate OS identities, keys, sockets and journals.
- The agent runtime cannot register authorizations and must not access the issuer socket.
- Signer APIs are typed and narrow; never add generic sign-transaction/sign-message endpoints.
- Signers derive transaction fields from the signed authorization; caller-provided arbitrary calldata is not trusted.
- Arc authorizations follow the Registry registration → confirmation → consumption → confirmation → payment → settlement-confirmation sequence.
- Generic execution-consume must not bypass Arc Registry confirmation.

## Chain and asset invariants

- Arc Mainnet chain ID is 5042.
- Canonical USDC ERC-20 address is pinned in code/config and deployment evidence.
- ERC-20 USDC uses 6 decimals; Arc native gas accounting uses 18 decimals.
- ERC-20 payments use zero native transaction value.
- Registry address/runtime hash must be checked against reviewed deployment evidence.
- Registry is not escrow and cannot prevent transfers submitted outside the integrated client/signer path.

## Merge and release discipline

- The unified Arc branch is a review/integration branch; it is not permission to deploy.
- Do not merge into main until current-main conflicts are resolved, security review is complete and fresh CI is green.
- CI/mock-RPC evidence must not be described as a live mainnet payment.
- Production key provisioning, host installation and live broadcasts require separate explicit approval.