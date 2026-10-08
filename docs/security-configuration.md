# Security configuration

Verigate is open by default so the demo and tests run with zero setup. For any
real deployment, turn on the controls below. Every flag is read from the
environment; boolean flags accept `1`, `true` or `yes`.

## Recommended production baseline

```bash
# API authentication: default-deny, fail closed if the key list is missing
export VERIGATE_API_KEYS="sha256:<hex-of-your-key>"   # comma-separated; plain or sha256:<hex>
export VERIGATE_REQUIRE_AUTH=1

# Issuer key: encrypted at rest, never written in plaintext
export VERIGATE_KEY_PASSPHRASE="<long random passphrase>"
export VERIGATE_REQUIRE_ENCRYPTED_KEY=1

# Executable authority only for agent-signed intents
export VERIGATE_REQUIRE_SIGNED_INTENT=1

# Policy changes need governance quorum (see README: governed policy)
export VERIGATE_REQUIRE_GOVERNED_POLICY=1

# Demo surfaces stay OFF (do not set these in production)
# VERIGATE_ENABLE_DEMO_ENDPOINTS, VERIGATE_ENABLE_DEMO_TAMPER
```

## Reference

| Variable | Default | Effect |
|---|---|---|
| `VERIGATE_API_KEYS` | unset (open) | Comma-separated keys, each plain or `sha256:<hex>`. Once set, every route requires a key (`Authorization: Bearer ...` or `X-API-Key`) except the public allowlist: `GET /health`, `GET /v1/public-key`, `GET /v1/governance/public-key`, `POST /v1/verify`, `POST /v1/evidence/manifest/verify`. Compared in constant time. Read on every request, so rotation needs no restart. A malformed list still locks the API instead of opening it. |
| `VERIGATE_REQUIRE_AUTH` | off | Fail closed: an unconfigured deployment refuses every non-public request instead of running open. |
| `VERIGATE_TENANT_API_KEYS` | unset | Tenant-scoped API credentials (JSON object keyed by tenant id) for multi-tenant deployments. |
| `VERIGATE_TENANT_KEY_DIR` | unset (single tenant) | Switches on multi-tenant issuer keys: each tenant gets its own signing key, selected by the `X-Verigate-Tenant` header. |
| `VERIGATE_TENANT_MASTER_SECRET` | unset | Master secret used by the tenant key provider. |
| `VERIGATE_KEY_PASSPHRASE` | unset | Encrypts the issuer private key at rest. |
| `VERIGATE_REQUIRE_ENCRYPTED_KEY` | off | Refuses plaintext issuer keys and never writes one. Pair with `VERIGATE_KEY_PASSPHRASE`. |
| `VERIGATE_REQUIRE_SIGNED_INTENT` | off | `POST /v1/authorize/capability` answers 403, so executable authority is issued only through `POST /v1/authorize/identity` and `POST /v1/actions/authorize`, which verify the agent's own signature. Capabilities bound to an identity are rejected on the unsigned path even when this flag is off. |
| `VERIGATE_REQUIRE_GOVERNED_POLICY` | off | Policy versions must be published through governance (quorum) rather than loaded directly. |
| `VERIGATE_GOVERNANCE_POLICY`, `_PRIVATE_KEY`, `_PUBLIC_KEY` | unset | Governance quorum policy and signing keys. |
| `VERIGATE_ALLOW_UNGOVERNED_ATTESTOR_BOOTSTRAP` | off | Explicit opt-in to bootstrap outcome attestors without governance. Leave unset in production. |
| `VERIGATE_ENABLE_DEMO_ENDPOINTS` / `VERIGATE_ENABLE_DEMO_TAMPER` | off | Judge-demo routes and tamper demo. Never enable in production. |
| `VERIGATE_POLICY`, `VERIGATE_DB`, `VERIGATE_PRIVATE_KEY`, `VERIGATE_PUBLIC_KEY` | `policies/default.yaml`, `data/verigate.db`, `keys/issuer.key`, `keys/issuer.pub` | File locations. |

## Which endpoint issues authority

| Endpoint | Issues executable authority? | Agent signature required? |
|---|---|---|
| `POST /v1/check`, `/v1/check/x402` | No (advisory decision) | No |
| `POST /v1/authorize`, `/v1/authorize/x402` | No (decision only) | No |
| `POST /v1/authorize/capability` | Yes | No. Disabled by `VERIGATE_REQUIRE_SIGNED_INTENT` |
| `POST /v1/authorize/identity` | Yes | Yes |
| `POST /v1/actions/authorize` | Yes | Yes |

Anyone can verify a signed decision offline with `POST /v1/verify` or the
standalone verifier; only the issuer public key is needed.
