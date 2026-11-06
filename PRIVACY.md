# Privacy Policy

Last updated: 2026-11-06

This policy explains how **Verigate Authority for Anna** and the open-source **Verigate** software process information. It describes the current implementation in this repository. It is not a promise that Anna, wallet providers, RPC providers, or other third parties follow the same practices; their own policies also apply.

- Project and source code: https://github.com/rudimentall1/verigate
- Security vulnerability reporting: https://github.com/rudimentall1/verigate/security/advisories/new
- Questions and general support: https://github.com/rudimentall1/verigate/issues

## 1. What Verigate Authority does

Verigate Authority is an authorization and execution-control application. It evaluates a proposed action against deterministic policy and authority rules and produces a signed Decision Receipt.

The possible policy decisions are:

- **ALLOW** — the exact action may proceed to the separate, explicit authorization step. ALLOW is not itself a wallet signature or proof that a transaction succeeded.
- **WARN** — the action requires review and does not receive execution authority.
- **BLOCK** — the action is denied and does not receive execution authority.

For an eligible ALLOW decision, the app can issue a short-lived, one-time, signed Execution Authorization after an explicit in-app confirmation. For supported native USDC transfers on Base and Ethereum, the ExecutionRouter verifies and consumes that exact authorization before the connected wallet is asked to review, sign, and submit the transaction. A separate user confirmation is required for the wallet-submission step.

Verigate does not hold wallet private keys, independently sign transactions, or broadcast wallet transactions. The connected wallet remains responsible for signing and submitting. Solana support in this Anna release is limited to policy checks and authorization; the Anna wallet-submission flow described above is currently limited to Base and Ethereum native USDC transfers.

**Enforcement boundary:** the execution controls apply only when an action is routed through the Verigate ExecutionRouter integration. A transaction or side effect submitted through a separate path that bypasses that router is outside this app's enforcement boundary.

## 2. Information processed

Depending on the action and enabled features, Verigate may process:

- The payment or action description entered by the user.
- Structured action fields, such as agent or capability identifiers, recipient/target, asset, network, amount, resource or purpose, and action metadata.
- Policy and authority context needed to evaluate the action, such as configured limits, allowlists, capability and identity references, prior recorded activity, and authorization state.
- The resulting decision, matched policy rules, timestamps, identifiers, signatures, and verification information.
- For supported EVM wallet transfers, the exact transaction details needed to bind the wallet request to the authorized action, including network/chain, token contract, destination, amount, and transaction data.

Do not enter seed phrases, private keys, wallet recovery material, passwords, or other secrets into the app. Verigate does not need them.

## 3. Anna AI and language-model processing

The Anna app uses the language-model capability supplied by the Anna app runtime to interpret natural-language requests, identify missing or ambiguous details, perform contextual risk analysis, and explain policy results.

The request text and relevant form/action details may therefore be sent to the model provider through Anna's runtime. This processing is subject to Anna's and the applicable model provider's terms and privacy practices. Verigate's developer does not operate that model service and does not receive the user's prompts through a Verigate-operated backend.

The model does not make the final authorization decision and cannot grant execution authority. Its contextual risk output is advisory; the deterministic Verigate policy and authority checks determine the final ALLOW, WARN, or BLOCK result. An advisory risk flag can make a result stricter, but cannot turn a policy denial into an approval.

## 4. Local processing, storage, and retention

The Verigate Executa performs policy evaluation and authorization operations within the installed agent runtime. The current Anna implementation uses local app data storage for its issuer key material and SQLite-backed state.

Depending on the features used, that local state can include:

- The installation's Ed25519 issuer private and public keys.
- Policy and policy-version records.
- Decision and authorization audit records, including action fields, decisions, matched rules, timestamps, and signatures.
- Capability, identity, delegation, authority-state, and governance records.
- Signed execution authorization artifacts and one-time nonce-consumption records.
- Execution receipts and related evidence records where those flows are used.

A preview/check operation is non-persistent as described in the app documentation: it does not create a new attempt record, although it can read existing history when applying history-based controls. The separate confirmed authorization operation re-evaluates the action and persists the applicable authorization and audit state. Consuming an execution authorization records its one-time use so it cannot be replayed.

The data directory is on the agent installation/runtime, not a Verigate-operated hosted database. The app may select a writable local data directory according to its runtime configuration. Anyone with access to that machine, agent environment, backups, or app data directory may be able to access the locally stored data. Protect that environment and its backups accordingly.

The current software does not define a universal automatic deletion schedule for these local records. They may remain until the operator deletes the app data or otherwise manages the installation's storage. Deleting local records or keys can affect audit history, verification, and the ability to use outstanding authorizations. Back up only what you need and protect backups as sensitive data.

## 5. Wallets, blockchain networks, and other third parties

When a supported wallet flow is used:

1. Verigate prepares and validates the exact action and its signed authorization.
2. The ExecutionRouter verifies and consumes the one-time authorization.
3. The app passes the resulting transaction request to the connected wallet.
4. The wallet independently presents the transaction for user review and signing. If the user signs and submits it, the wallet and relevant network infrastructure process it.

Verigate does not receive or store the wallet's private key. The connected wallet, its provider, the selected blockchain network, RPC services, block explorers, and any other services used by the wallet may process transaction data, network identifiers, wallet addresses, IP addresses, and related technical information under their own policies. Blockchain transactions may be public, persistent, and difficult or impossible to remove.

A successful authorization or router-consumption response does not mean that the wallet signed the transaction, that it was broadcast, confirmed, or finalized. The wallet and network determine those later outcomes.

## 6. Data sharing, analytics, and advertising

The Verigate project does not operate a hosted service or central database for the Anna app and does not intentionally send app records to a Verigate-operated server.

The app is not designed to include advertising, behavioral profiling, or product analytics. The natural-language processing described in Section 3 and the wallet/network interactions described in Section 5 are necessary third-party processing paths when those features are used. Anna, model providers, wallet providers, RPC providers, and blockchain networks operate independently and may collect information under their own terms.

The project does not sell personal information.

## 7. Open-source and self-hosted deployments

The Verigate repository also contains standalone libraries, command-line tools, APIs, and execution adapters. When you run or deploy those components yourself, you or the operator of that environment control the infrastructure, configuration, logs, database, keys, backups, and retention practices.

Some standalone deployment features can expose an HTTP API or connect to external networks and adapters. Their data flows depend on the components you enable and how you configure them. Review the deployment and security documentation before exposing an instance to a network. An incorrectly configured public deployment may expose data or authority operations.

The source code is available for inspection under its repository license. The presence of open-source code does not by itself guarantee that a third-party deployment is configured securely.

## 8. Security

Verigate uses cryptographic signatures and execution-boundary checks, but no software or storage environment can be guaranteed completely secure. Keep the agent runtime, operating system, wallet, signing environment, and backups protected. Do not share issuer private keys or sensitive local data.

For vulnerability reports, use the repository's private security advisory process:
https://github.com/rudimentall1/verigate/security/advisories/new

Please do not publish exploitable vulnerability details in a public issue before a fix is available.

## 9. Children

Verigate Authority is a developer and financial-action control tool and is not directed at children.

## 10. Changes to this policy

This policy may be updated when the app's functionality, integrations, or data handling changes. The “Last updated” date at the top indicates the latest revision. The policy in the repository may describe a newer version than an app build already installed by a user; consult the release and app version information when assessing which functionality applies.
