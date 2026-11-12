# Arc Agent Signer Service

**Status:** design and implementation gate; not production-ready until code, adversarial tests and CI are complete.

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

## Implementation status (2026-11-12)

- Implemented: typed newline-delimited JSON protocol over a Unix-domain socket, 64 KiB request cap, one request per connection, socket mode 0660, refusal to replace an existing socket path, role checks, signed-authorization verification, internally derived transaction fields, durable reservation before adapter invocation, replay response for completed operations, and fail-closed unresolved reservations.
- Implemented: ethers v6 adapter with Arc chain-ID check, pinned Registry address and runtime bytecode hash verification at startup, live fee-data validation, gas estimation, configured gas/fee ceilings, pending nonce lookup, serialized local broadcasts, receipt status/hash checks, confirmation wait and actual native-cost accounting.
- Implemented: Linux daemon entrypoint with file-based private-key loading, owner/mode checks, role-specific configuration, no key in command-line arguments or environment variables, and startup failure if the Registry pin or fee policy is invalid.
- Implemented tests: policy authorization, role separation, daily budget, socket replay and request validation, typed client operations and server errors, adapter chain/code-hash/issuer/fee/gas checks and receipt accounting, and full mocked Verigate confirmation orchestration through signer clients.
- Not implemented: systemd units, installation/rollback scripts, automated OS account and group provisioning, clean-room Linux install validation, and live Arc broadcast test. The current tests use mocked provider/wallet objects; they are not live-chain verification.
- This remains an OS-isolated signer design, not an HSM and not protection against root/host compromise. Separate Linux users, groups, key files, journals and socket paths must be provisioned before the two role instances are safe to operate.

## Interface requirements

- Local Unix domain socket only. No TCP listener and no public HTTP port.
- Filesystem permissions are the caller access-control boundary. Socket mode 0660; signer key mode 0600; journal mode 0600.
- Typed operations only: `register`, `consume`, `payment`. No generic sign-message, sign-transaction or caller-supplied arbitrary calldata method.
- Every request carries the complete Verigate Execution Authorization. The signer independently verifies its Ed25519 signature against an out-of-band pinned public key.
- The signer independently derives Registry calldata and USDC transfer calldata. It does not trust caller-supplied destination, calldata, chain ID, value, gas or fee fields.
- Role policy restricts the issuer instance to `register`; the agent instance to `consume` and `payment`.
- The signer pins Arc Mainnet chain ID 5042, the reviewed Registry address and runtime code hash, and canonical Arc USDC address `0x3600000000000000000000000000000000000000`.
- Agent signer address must equal the signed payment envelope's `from` address. Issuer signer address must equal the configured enabled Registry issuer.
- Authorization validity is checked at signing time. The signer rejects malformed, forged, expired, not-yet-valid and over-300-second authorizations.

## Replay, crash and idempotency

Use a durable append-only operation journal. Before broadcast, persist and fsync a reservation keyed by authorization ID plus operation. Immediately after the RPC returns a transaction hash, append and fsync a `broadcast` record containing that hash, before waiting for the receipt. After receipt verification, append and fsync the terminal outcome.

- A repeated operation with a completed record returns the existing result; it never broadcasts again.
- A reservation without a recorded transaction hash is ambiguous (the process may have crashed after broadcast but before the hash was durably recorded). A `broadcast` record contains the exact transaction hash but is still unresolved until receipt verification is persisted. Both states reject retries and require operator reconciliation; never auto-retry an unresolved operation.
- Serialize journal mutation and requests. Daily budget accounting includes reserved and broadcast-but-unresolved operations. Fail closed on lock, parse, fsync or persistence errors.
- Do not permit an operator to clear the journal as a routine retry mechanism. Reconciliation must inspect the nonce, transaction pool, chain receipt and Registry state and leave an audit record.

## Fee and spend policy

The signer must set and enforce transaction limits itself, not accept them from the agent:

- Per-operation gas limit.
- Maximum fee per gas.
- Maximum priority fee per gas.
- Maximum native-token cost per transaction.
- Per-instance daily native-token budget and optional rate limit. Each signer role enforces its own budget from its own journal; the system-wide daily ceiling is the sum of the issuer and agent budgets. This is not a shared global budget. A strict shared ceiling requires a shared ledger or budget broker before deployment.

No fee numbers are hard-coded in this specification. The initial values must be measured from representative Arc registration, consumption and USDC transfer receipts and reviewed by the operator. Startup must fail if required limits are missing, malformed, internally inconsistent or exceed the configured cost budget. The signer must fail closed if live fee data cannot be validated.

## Linux deployment model

The checked-in systemd template is `deploy/systemd/verigate-arc-signer@.service`. Instantiate it separately as `verigate-arc-signer@issuer.service` and `verigate-arc-signer@agent.service`.

- Dedicated Linux users and primary groups: `verigate-signer-issuer` and `verigate-signer-agent`.
- Only the intended agent runtime user is added to group `verigate-signer-agent`. The issuer socket must be accessible only to the operator/issuer caller.
- Private key files are owned by the matching signer user and mode 0600 (or stricter); key files must not be shared between roles.
- Runtime paths: `/run/verigate-signer-issuer/signer.sock` and `/run/verigate-signer-agent/signer.sock`, directory mode 0750, socket mode 0660.
- Journals: `/var/lib/verigate-signer-issuer/ops.jsonl` and `/var/lib/verigate-signer-agent/ops.jsonl`; each role has its own state. The parent directory must be owned by that signer user and mode 0700; the journal must be a regular, single-link file owned by that user and mode 0600 or stricter. Symlinks, hard links and broader permissions are rejected. Each journal enforces only its own role budget; configure the two limits so their sum is within the intended total daily spend ceiling.
- Each `/etc/verigate-signer/{issuer,agent}.env` file is root-owned and readable by the service manager. It sets `VERIGATE_SIGNER_ROLE`, `VERIGATE_SIGNER_SOCKET`, `VERIGATE_SIGNER_JOURNAL`, `VERIGATE_SIGNER_PRIVATE_KEY_FILE`, `VERIGATE_AUTH_PUBLIC_KEY_FILE`, `VERIGATE_ARC_RPC_URL`, `VERIGATE_ARC_ISSUER_ADDRESS`, `VERIGATE_ARC_REGISTRY_ADDRESS`, `VERIGATE_ARC_REGISTRY_CODE_HASH`, and all six `VERIGATE_SIGNER_*` fee/confirmation limits.
- The signer entrypoint rejects a private key file not owned by its service user or readable by group/other. It rejects symlinks and non-regular files. It also requires the journal directory to be owned by the signer user and mode 0700; journal reads reject symlinks, hard links, foreign ownership and group/other permissions.
- Verified Registry pin: `0x4D09CdD490c1Ce48BCB6DA5c1A6Bf41E2f5e853D`. The read-only deployment verification in run [43160472757](https://github.com/rudimentall1/verigate/actions/runs/43160472757) confirmed this exact address, Arc chain ID 5042, owner, enabled issuer and deployed runtime hash. The signer requires `VERIGATE_ARC_REGISTRY_ADDRESS` and rejects any value that differs from this pinned deployment.
- systemd hardening: no-new-privileges, private tmp, strict filesystem protections, restricted writable paths, no ambient capabilities, and restricted address families.
- Do not use Docker as a prerequisite.
- Do not change, restart or stop FLOP, AegisForge, OWNERA or unrelated services.

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
- A clean-room installation test passes on a disposable Linux environment.
- Gensyn2 inventory is inspected before any write. Existing processes and project directories are left untouched.
- Installation and rollback steps are documented and tested.
- No mainnet transaction is broadcast during installation. Live payment requires a separate explicit decision after fee limits are measured.
- Do not call this an HSM or claim protection against root/host compromise. This is an OS-isolated constrained signer service; KMS/HSM remains a stronger future deployment option.
