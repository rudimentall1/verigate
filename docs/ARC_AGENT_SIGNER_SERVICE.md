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
- Implemented tests: agent payment request, replay without a second adapter call, issuer-only operation rejection by an agent role, arbitrary caller-supplied transaction fields rejection, socket permissions, and existing-path refusal.
- Not implemented: production ethers adapter, encrypted/private-key loading, nonce manager, Registry runtime-bytecode verification in signer startup, systemd units, installation/rollback scripts, and OS account provisioning.
- The socket module is transport/policy orchestration only. It does not yet sign or broadcast a transaction. The injected adapter is a trusted boundary and must enforce live fee data, nonce handling, transaction construction, broadcast, receipt status and finality before this can be treated as an operational signer.

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

Use a durable append-only operation journal. Before broadcast, persist and fsync a reservation keyed by authorization ID plus operation. After submission, persist and fsync the transaction hash and terminal receipt outcome.

- A repeated operation with a completed record returns the existing result; it never broadcasts again.
- A reservation without a recorded transaction hash is ambiguous (the process may have crashed after broadcast). Reject and require operator reconciliation. Never auto-retry an ambiguous operation.
- Serialize journal mutation and requests. Fail closed on lock, parse, fsync or persistence errors.
- Do not permit an operator to clear the journal as a routine retry mechanism. Reconciliation must inspect the nonce, transaction pool, chain receipt and Registry state and leave an audit record.

## Fee and spend policy

The signer must set and enforce transaction limits itself, not accept them from the agent:

- Per-operation gas limit.
- Maximum fee per gas.
- Maximum priority fee per gas.
- Maximum native-token cost per transaction.
- Aggregate daily native-token budget and optional rate limit.

No fee numbers are hard-coded in this specification. The initial values must be measured from representative Arc registration, consumption and USDC transfer receipts and reviewed by the operator. Startup must fail if required limits are missing, malformed, internally inconsistent or exceed the configured cost budget. The signer must fail closed if live fee data cannot be validated.

## Gensyn2 deployment model

- Dedicated Linux user: `verigate-signer`.
- Dedicated access group: `verigate-agent`; only the intended agent runtime user is a member.
- Signer key directory: owned by `verigate-signer`, mode 0700; private key file mode 0600.
- Runtime directory: `/run/verigate-signer`, mode 0750.
- Unix socket: `/run/verigate-signer/signer.sock`, mode 0660, group `verigate-agent`.
- Separate service instance, user, key path, journal and socket for issuer and agent roles.
- systemd hardening: no-new-privileges, private tmp, strict filesystem protections, restricted writable paths, and no ambient capabilities.
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
