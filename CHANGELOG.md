# Changelog

## Anna app 0.1.9 (real Cloud Agent test feedback)

- Fixed: on the real Anna model the answer to the intake step was occasionally not valid JSON, which showed "Anna AI could not read this request" on a perfectly good request. The app now allows more room for the answer, tolerates trailing commas, and retries once with a stricter reminder before giving up; the message says that Anna's answer, not the user's request, could not be read.
- Fixed: the previous "Anna AI: ..." summary stayed visible after a new check failed; it is now cleared at the start of every check.
- Fixed: the list of missing details could repeat itself (for example a recipient question twice). It now has one deterministic question per missing detail.
- Changed: removed the unused `storage` host permission, so the permission dialog only asks for what the app needs (`llm.complete` and the Verigate tool). The Executa is unchanged (0.1.8).
- Tests: UI flow tests for retry, repeated failure, cleared stale text and non-repeating questions.

## Anna app 0.1.8 (review feedback: AI role and recipient validation)

- Fixed: a malformed recipient such as `0xabc`, an empty recipient or a zero amount was ALLOWed and received a signed receipt. The policy engine now validates the recipient address for the network before any limit is evaluated: EVM addresses must be `0x` plus 40 hex characters (and pass the EIP-55 checksum when mixed-case), Solana addresses must be base58 for 32 bytes, the zero address and zero or non-finite amounts are rejected. The check lives in the engine (`core/payee.py`, `core/rules.py`) and is enabled by the Anna policy (`policies/anna.yaml`); the default policy keeps it off for backwards compatibility. A well-formed address still does not prove the recipient is safe.
- Fixed: a `NaN` amount crashed the plugin with an internal database error; it now returns a clean `invalid arguments` error.
- Changed: a check is now a simulation. Nothing is recorded, so the same request always gets the same answer and repeated tests do not consume daily budget.
- Changed: Anna AI is part of the main flow. It reads the plain-language request, asks for missing or unclear details (the check does not run until they are provided or confirmed), flags risks in the text such as instructions aimed at the checker, and explains the result with a comparison against the policy limits. AI input is advisory and can only make a result stricter: a flag raises ALLOW to WARN and an advisory BLOCK is ignored. The final decision always comes from the deterministic engine.
- Added: `verigate_policy_summary` tool (read-only limits), `ai_flags_json` argument, `persist=False` simulation mode in the engine, 18 regression tests, an end-to-end UI test (`scripts/test_anna_ui.mjs`, real app and real plugin with a scripted LLM) and a CI job for it.

## Anna app 0.1.3 (Executa fixes for review feedback)

- Fixed: Anna could not install the Executa (`describe handshake failed`). `describe` returned `parameters` as a JSON Schema object and had no `description`; it now follows Executa protocol 1.1 (parameters list, description, author, license).
- The plugin answers `describe` without touching the filesystem or loading the engine (cold start 0.6 s, limit 5 s) and falls back to a writable data directory when the install directory is read-only.
- Protocol-correct errors: -32700 parse error, -32601 unknown tool, -32602 missing arguments; bad input no longer kills the process; clean SIGTERM exit.
- The binary smoke test now checks `describe` against the protocol, cold-start time and error handling, so this class of bug fails CI.

## v0.1.0

First tagged release of Verigate, the agent authority control plane.

### Authority and attestation
- Signed ALLOW/BLOCK decisions with offline verification (`/v1/verify`, standalone verifier, `verigate verify` with an explicit trusted issuer key).
- Agent identities with agent-signed action intents (`/v1/authorize/identity`, `/v1/actions/authorize`); capability grants bound to an identity.
- Single-use execution nonces; double-spend prevention covered by a real multi-process test.
- Portable authority proof package with tamper detection.
- Governed policy versions with quorum publishing.

### Security hardening
- API-key authentication, default-deny, with fail-closed mode (`VERIGATE_REQUIRE_AUTH`) and tenant-scoped credentials.
- Multi-tenant issuer keys (`VERIGATE_TENANT_KEY_DIR`).
- Issuer private key encrypted at rest (`VERIGATE_KEY_PASSPHRASE`, `VERIGATE_REQUIRE_ENCRYPTED_KEY`).
- `VERIGATE_REQUIRE_SIGNED_INTENT` closes the unsigned capability authorization path.
- Exact `Decimal` arithmetic for policy caps; NaN, infinity and negative amounts rejected.
- Fixed: attestations from `/v1/check` could not be verified independently because `context_sha256` was missing from the response.
- Fixed: unbounded cycle traversal in the intent graph (denial of service).

### Integrations
- Anna app `verigate-authority`, packaged as an Executa.
- x402 payment parsing, Solana Devnet execution, CMC RWA fixture mode.

### Tooling
- CI runs the full suite, the end-to-end demo and an API smoke check. 447 tests.
- Fixed: a CLI test depended on a locally generated key file and failed on fresh checkouts.

See [docs/security-configuration.md](docs/security-configuration.md) for production settings.
