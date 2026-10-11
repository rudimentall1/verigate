# Security Policy

## Reporting a vulnerability

Please do not open a public issue for security problems.

Report privately through GitHub: open the **Security** tab of this repository and choose
**Report a vulnerability** (https://github.com/rudimentall1/verigate/security/advisories/new).

Please include the affected component and commit or version, steps to reproduce, and the
impact you observed. We aim to acknowledge reports within 5 business days and will keep you
informed while we investigate. Reporters who want credit will be credited in the fix.

## Supported versions

Security fixes are applied to `main` and released as the next `v0.1.x` patch. Older tags are
not maintained.

## Scope

In scope: authorization decisions, signing and verification, execution nonce consumption and
the execution router, API authentication and tenant isolation, issuer key handling, and the
standalone verifier and CLI.

Out of scope (documented limits, see `docs/threat-model.md`):

- Effects created inside a trusted handler (transitive executor confinement is not claimed).
- Deployments that leave the API open (no `VERIGATE_API_KEYS` / `VERIGATE_REQUIRE_AUTH`) or
  that enable demo endpoints. See `docs/security-configuration.md`.
- Volumetric denial of service against an unprotected deployment.
- Vulnerabilities in third-party dependencies without a demonstrated impact on Verigate
  (please report those upstream).

## Hardening a deployment

Follow the production baseline in `docs/security-configuration.md`.
