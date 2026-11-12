# Arc Agent Signer Service

**Status:** implementation and CI-tested on a disposable Linux runner; not production-ready until target-host identity/ACL review, real Arc fee sampling, and controlled deployment gates are complete.

## Purpose

Remove unrestricted EVM private-key access from the autonomous agent runtime. The agent may request a narrowly defined Arc operation using a signed Verigate Execution Authorization. It must not submit arbitrary transaction data to a generic signing endpoint.

This service is not a wallet firewall. It protects the integrated Verigate execution path while its host, OS account, key permissions and service boundary remain trusted.

## Trust boundaries

Run two instances of the same constrained signer implementation under separate OS identities and separate key files:

| Instance | Permitted operation | Key |
|---|---|---|
| Registry issuer signer | Register one exact authorization at the pinned Registry | Operator-controlled issuer key |
| Agent executor signer | Consume that authorization and transfer the exact authorized USDC amount | Agent-scoped EVM key |
| Verigate API | Authorize and verify; never signs or broadcasts | No EVM private key |
| Agent/model process | Submit signed intent and request approved operations | No EVM private key |

The issuer instance must not share its key file, Unix socket, process identity or writable state with the agent instance. The agent instance must never be able to request Registry registration.

The application-side orchestration must preserve that split. Run `registerArcAuthorizationWithIssuerSignerClient` only in the operator-controlled issuer controller; it requires only the issuer socket and returns the signed authorization plus the confirmed registration transaction hash. Hand those values to the agent runtime, which calls `executeRegisteredArcPaymentWithAgentSignerClient` using only the agent socket. The agent phase independently re-confirms registration through Verigate before consuming and paying. The agent process does not need issuer-socket permissions. The compatibility wrapper `executeAuthorizedArcPaymentWithSignerClients` requires both clients in one process and is for a trusted coordinator only; do not deploy that wrapper inside the autonomous agent runtime.

## Implementation status (2026-11-12)

- Implemented: typed newline-delimited JSON protocol over a Unix-domain socket, 64 KiB request cap, one request per connection, socket mode 0660, refusal to replace an existing socket path, role checks, signed-authorization verification, internally derived transaction fields, durable reservation before adapter invocation, replay response for completed operations, and fail-closed unresolved reservations.
- Implemented: ethers v6 adapter with Arc chain-ID check, pinned Registry address and runtime bytecode hash verification at startup, live fee-data validation, gas estimation, configured gas/fee ceilings, pending nonce lookup, serialized local broadcasts, receipt status/hash checks, confirmation wait, receipt hash/sender/destination/block checks and actual native-cost accounting.
- Implemented: Linux daemon entrypoint with file-based private-key loading, owner/mode checks, role-specific configuration, no key in command-line arguments or environment variables, explicit live `eth_chainId` verification (not merely the static ethers network setting), and startup failure if the Registry pin or fee policy is invalid.
- Implemented tests: policy authorization, role separation, daily budget, socket replay and request validation, typed client operations and server errors, adapter chain/code-hash/issuer/fee/gas checks and receipt accounting, and full mocked Verigate confirmation orchestration through signer clients.
- Implemented and CI-tested: hardened systemd unit template, guarded install/rollback scripts, disposable Linux account/config/key permission smoke test, systemd unit validation, positive/negative Unix-socket group ACL checks, real systemd manager startup/restart with a disposable socket service, and startup/restart of the actual `run_arc_signer.mjs` daemon against a local HTTPS mock Arc RPC. A separate full-flow smoke test starts both issuer and agent signer daemons under separate systemd users, issues a valid ephemeral Ed25519 authorization, executes issuer `register` → agent `consume` → agent exact USDC `payment` against a stateful local mock RPC, checks that each role rejects the other's forbidden operation, and repeats each completed operation to prove journal replay without rebroadcast. The mock RPC accepts exactly three local raw transactions and asserts destination, selectors, role addresses, same authorization ID/intent hash and exact payment calldata. No public RPC or mainnet transaction is used in this test. These are runtime tests on disposable CI workers, not a production deployment on Gensyn2 or live-chain signer operation.
- This remains an OS-isolated signer design, not an HSM and not protection against root/host compromise. Separate Linux users, groups, key files, journals and socket paths must be provisioned before the two role instances are safe to operate.

## Interface requirements

- Local Unix domain socket only. No TCP listener and no public HTTP port.
- Filesystem permissions are the caller access-control boundary. Socket mode 0660; signer key mode 0600; journal mode 0600.
- Typed operations only: `register`, `consume`, `payment`. No generic sign-message, sign-transaction or caller-supplied arbitrary calldata method.
- Every request carries the complete Verigate Execution Authorization. The signer independently verifies its Ed25519 signature against an out-of-band pinned public key.
- The signer independently derives Registry calldata and USDC transfer calldata. It does not trust caller-supplied destination, calldata, chain ID, value, gas or fee fields.
- Role policy restricts the issuer instance to `register`; the agent instance to `consume` and `payment`. The agent journal refuses `payment` unless `consume` for the same canonical authorization ID has a completed receipt record.
- The signer pins Arc Mainnet chain ID 5042, the reviewed Registry address and runtime code hash, and canonical Arc USDC address `0x3600000000000000000000000000000000000000`.
- Agent signer address must equal the signed payment envelope's `from` address. Issuer signer address must equal the configured enabled Registry issuer.
- Authorization validity is checked when the request is accepted and revalidated after RPC fee/gas/nonce preflight immediately before broadcast. The signer rejects malformed, forged, expired, not-yet-valid and over-300-second authorizations.

## Replay, crash and idempotency

Use a durable append-only operation journal. Before broadcast, persist and fsync a reservation keyed by authorization ID plus operation. Immediately after the RPC returns a transaction hash, append and fsync a `broadcast` record containing that hash, before waiting for the receipt. After receipt verification, append and fsync the terminal outcome.

- Authorization IDs are normalized to lowercase bare bytes32, and journal keys also bind the signed authorization digest. Prefix/case variants cannot create separate replay records, while two distinct signed intents reusing one authorization ID cannot share a consume/payment gate.
- A repeated operation with a completed record returns the existing result; it never broadcasts again.
- A reservation without a recorded transaction hash is ambiguous (the process may have crashed after broadcast but before the hash was durably recorded). A `broadcast` record contains the exact transaction hash but is still unresolved until receipt verification is persisted. Both states reject retries and require operator reconciliation; never auto-retry an unresolved operation.
- Serialize journal mutation and requests. Daily budget accounting includes reserved and broadcast-but-unresolved operations even across UTC midnight, because a pending transaction may be mined on the following day. Completed operations are charged by their UTC settlement day. Fail closed on lock, parse, fsync or persistence errors.
- Do not permit an operator to clear the journal as a routine retry mechanism. Reconciliation must inspect the nonce, transaction pool, chain receipt and Registry state and leave an audit record.

## Fee and spend policy

The signer must set and enforce transaction limits itself, not accept them from the agent:

- Per-operation gas limit.
- Maximum fee per gas.
- Maximum priority fee per gas.
- Maximum native USDC cost per transaction (native 18-decimal units).
- Per-instance daily native USDC budget, enforced by UTC calendar day, and optional rate limit. Arc native USDC uses 18 decimals for gas accounting; the canonical USDC ERC-20 interface used for application transfers uses 6 decimals. `gasUsed × effectiveGasPrice`, `maxNativeCost` and `dailyNativeBudget` are native 18-decimal USDC base units. Fee-per-gas values (`maxFeePerGas`, `maxPriorityFeePerGas`) remain EVM wei-per-gas values. Convert native fee totals by dividing by 10^12 before expressing them in six-decimal ERC-20 USDC units. Each signer role enforces its own budget from its own journal; the system-wide daily ceiling is the sum of issuer and agent budgets. This is not a shared global budget. A strict shared ceiling requires a shared ledger or budget broker before deployment.

No production fee limits are set. `scripts/verify_arc_fee_samples.mjs` now retrieves three historical Verigate Registry receipts and one canonical ERC-20 USDC transfer from the separate Agentic Wallet Guardian v3 project, using read-only JSON-RPC. It verifies each transaction's destination and method selector, then reports gas used, effective gas price and total native USDC fee in 18-decimal units, alongside the six-decimal equivalent. The Guardian transaction is fee-only reference data and must never be described as a Verigate payment. The script is included in CI; its output is an evidence sample only, not an automatic fee policy. Before choosing values, collect and compare actual registration, consumption and USDC transfer receipts, account for price variation, then set per-operation and daily ceilings with a review margin. Startup must fail if required limits are missing, malformed, internally inconsistent or exceed the configured cost budget. The signer must fail closed if live fee data cannot be validated.

## Linux deployment model

The checked-in systemd template is `deploy/systemd/verigate-arc-signer@.service`. Instantiate it separately as `verigate-arc-signer@issuer.service` and `verigate-arc-signer@agent.service`.

- Dedicated Linux users and primary groups: `verigate-signer-issuer` and `verigate-signer-agent`.
- Only the intended agent runtime user is added to group `verigate-signer-agent`. The issuer socket must be accessible only to the operator/issuer caller.
- Private key files are owned by the matching signer user and mode 0600 (or stricter); key files must not be shared between roles.
- Runtime paths: `/run/verigate-signer-issuer/signer.sock` and `/run/verigate-signer-agent/signer.sock`, directory mode 0750, socket mode 0660.
- Journals: `/var/lib/verigate-signer-issuer/ops.jsonl` and `/var/lib/verigate-signer-agent/ops.jsonl`; each role has its own state. The parent directory must be owned by that signer user and mode 0700; the journal must be a regular, single-link file owned by that user and mode 0600 or stricter. Symlinks, hard links and broader permissions are rejected. Each journal enforces only its own role budget; configure the two limits so their sum is within the intended total daily spend ceiling.
- Each `/etc/verigate-signer/{issuer,agent}.env` file is root-owned and readable by the service manager. It sets `VERIGATE_SIGNER_ROLE`, `VERIGATE_SIGNER_SOCKET`, `VERIGATE_SIGNER_JOURNAL`, `VERIGATE_SIGNER_PRIVATE_KEY_FILE`, `VERIGATE_AUTH_PUBLIC_KEY_FILE`, `VERIGATE_ARC_RPC_URL`, `VERIGATE_ARC_ISSUER_ADDRESS`, `VERIGATE_ARC_REGISTRY_ADDRESS`, `VERIGATE_ARC_REGISTRY_CODE_HASH`, and all six `VERIGATE_SIGNER_*` fee/confirmation limits.
- The signer entrypoint rejects a private key file not owned by its service user or readable by group/other. It rejects symlinks and non-regular files. It also requires the journal directory to be owned by the signer user and mode 0700; journal reads reject symlinks, hard links, foreign ownership and group/other permissions. The journal lock records PID, Linux boot ID and process start ticks. `scripts/recover_arc_signer_lock.mjs` supports inspect-only mode and explicit stale-lock recovery; it refuses live/ambiguous/unsafe lock files and never changes journal operation records. See `deploy/arc-signer/LOCK-RECOVERY.md`.
- Verified Registry pin: `0x4D09CdD490c1Ce48BCB6DA5c1A6Bf41E2f5e853D`. The read-only deployment verification in run [43160472757](https://github.com/rudimentall1/verigate/actions/runs/43160472757) confirmed this exact address, Arc chain ID 5042, owner, enabled issuer and deployed runtime hash. The signer requires `VERIGATE_ARC_REGISTRY_ADDRESS` and rejects any value that differs from this pinned deployment.
- systemd hardening: no-new-privileges, private tmp, strict filesystem protections, restricted writable paths, no ambient capabilities, and restricted address families. The unit resolves Node through `/usr/bin/env` using an explicit system-wide PATH; Node must be installed in `/usr/local/bin` or `/usr/bin`, not only inside a user-specific shell profile.
- Do not use Docker as a prerequisite.
- Do not change, restart or stop FLOP, AegisForge, OWNERA or unrelated services.

### Installer and rollback procedure (not yet executed)

The scripts assume the repository is checked out at `/opt/verigate`. The config and key parent directories are root-owned mode 0711 so signer users can traverse to their own key files without listing the directory. The scripts are intentionally staged:

1. Review `deploy/arc-signer/install.sh`. Run `sudo bash deploy/arc-signer/install.sh --provision-accounts` only when explicitly approved. This creates the two dedicated system users/groups and private state/config directories. It does not create keys. Existing signer accounts are accepted only with the matching primary group, home `/nonexistent` and shell `/usr/sbin/nologin`.
2. Provision distinct EVM private-key files and separate copies of the pinned Verigate authorization public key at the paths in the role templates. Each file must be owned by its matching signer account and mode 0600. The signer can traverse the root-owned mode-0711 parent directories but cannot list their contents. Key generation/import is an operator action and is not automated by these scripts.
3. Copy `issuer.env.example` and `agent.env.example` to `/etc/verigate-signer/{issuer,agent}.env`. Replace every placeholder, measure fee limits from real representative receipts, verify the issuer address, then set owner root:root and mode 0640 (the installer accepts only 0600 or 0640, whitelists the required variable names, rejects duplicates and private-key environment values). Never put private keys in environment files.
4. Run `sudo bash deploy/arc-signer/install.sh --check`. It is read-only and must pass for both roles.
5. After independent review, run `sudo bash deploy/arc-signer/install.sh --apply`. It installs the unit template and reloads systemd only. It does not enable or start either service.
6. Before starting the agent signer, separately grant only the intended agent runtime identity access to the agent socket group. Do not grant it access to the issuer socket or either key file. Review the actual caller identity and group membership first.
7. To roll back, run `sudo bash deploy/arc-signer/rollback.sh --check`, inspect the plan, then `sudo bash deploy/arc-signer/rollback.sh --apply`. Rollback stops/disables the two signer units and removes the unit template. It intentionally preserves keys, env files, journals, logs and service accounts for forensic review.

The example environment files contain deliberate placeholders and will fail installer validation until replaced. No fee ceilings are supplied here: derive and review them from actual Arc receipts; fee totals and spend budgets use 18-decimal native USDC units, while fee-per-gas configuration is wei per gas. The scripts require GNU/Linux utilities including systemd, GNU `stat`, `useradd` and `groupadd`. CI has validated the installer/rollback, real systemd service startup/restart, actual signer daemon initialization against a local mock Arc RPC, and positive/negative socket ACL behavior. This is not a deployment on the target host or live signer broadcast.

## Arc fee units and receipt evidence

Arc exposes one USDC balance through two interfaces. Native USDC, which funds gas and native value, has 18 decimals. The ERC-20 contract at `0x3600000000000000000000000000000000000000` has 6 decimals. The signer computes actual transaction cost as `gasUsed × effectiveGasPrice`; this is native USDC in 18-decimal units. Do not compare that integer directly with ERC-20 `transfer` amounts or six-decimal ledger entries. Divide native values by `10^12` when converting to six-decimal USDC units.

The read-only receipt sampler checks three historical Verigate Registry lifecycle transactions (two registrations and one consumption) plus one canonical ERC-20 USDC transfer from the separate Agentic Wallet Guardian v3 project. The latter is strictly a gas-cost reference, not evidence of a Verigate-authorized payment. The sampler validates transaction destination and method selector, then retrieves receipt fee fields. It does not send transactions. These four samples help estimate the payment operation cost, but one separate-project transfer is not a substitute for a Verigate-controlled payment receipt; production payment limits still require a real receipt and an explicit operator review.

## Required adversarial test matrix

1. Valid signed authorization and role-appropriate operation.
2. Invalid Ed25519 signature, malformed signature and wrong pinned public key.
3. Expired, future-issued and overlong authorization.
4. Wrong chain, Registry, Registry runtime hash or USDC contract.
5. Wrong agent sender, issuer address, recipient, amount, decimals or calldata.
6. Arbitrary destination, selector, native value, gas or fee fields supplied by caller.
7. Issuer attempting consume/payment; agent attempting registration.
8. Duplicate authorization/operation, concurrent duplicate requests and restart replay.
9. Crash after reservation and before broadcast; crash after broadcast and before hash persistence.
10. Gas limit, max fee, priority fee, per-operation cost and daily budget violations.
11. RPC timeout, malformed fee data, nonce conflict, reverted transaction and receipt/hash mismatch.
12. Journal corruption, permission failure, disk full and fsync failure.
13. Agent process cannot read either key file or access the issuer socket.
14. Service has no TCP listener and cannot sign arbitrary payloads.

## Release gates

- Implementation and tests are reviewed on a dedicated GitHub branch.
- Full repository CI passes on the exact branch head.
- The install/rollback scripts and unit syntax pass on a disposable Linux runner; actual systemd service start/stop/restart and role-specific socket ACL behavior must still be validated before deployment.
- Gensyn2 inventory is inspected before any write. Existing processes and project directories are left untouched.
- Installation and rollback steps are documented and tested.
- No mainnet transaction is broadcast during installation. Live payment requires a separate explicit decision after fee limits are measured.
- Do not call this an HSM or claim protection against root/host compromise. This is an OS-isolated constrained signer service; KMS/HSM remains a stronger future deployment option.
