# Changelog

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
