# Render deployment runbook (pre-deployment; not yet deployed)

This document describes a cautious first deployment of the Verigate FastAPI service on Render. It does not create a Render service, provision storage, or claim that a hosted API exists.

## 1. Service configuration

Create a **separate Web Service** for this repository. Do not repurpose `verigate-portaldot-explorer`: that service runs the Node.js explorer, not this Python API.

- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`
- Instance count: one instance for the initial SQLite-backed deployment
- Persistent disk: required; mount at `/var/data`

Do not treat the service as deployable until the dependency-install check in section 4 passes. A successful build alone does not prove the authorization path works.

### Cost and persistence gate

Render Free web services have an ephemeral filesystem and cannot attach persistent disks. A free Render Postgres database expires after 30 days, and this repository's current `Storage` implementation uses SQLite rather than PostgreSQL. Therefore, **the current SQLite deployment plan requires a paid Render web service with a persistent disk**. Do not deploy this configuration on Render Free and do not point it at a temporary SQLite path.

If a paid service is not an option, stop before creating a service. The alternative is a deliberate storage migration to a durable database supported by the application, with nonce atomicity and restart/replay tests; changing an environment variable alone is not a migration.

Reference: [Render free instance limitations](https://render.com/docs/free).

## 2. Persistent state and key paths

SQLite state and issuer/governance keys must survive restarts and redeploys. Configure these paths on the mounted disk:

```text
VERIGATE_DB=/var/data/verigate/verigate.db
VERIGATE_PRIVATE_KEY=/var/data/verigate/keys/issuer.key
VERIGATE_PUBLIC_KEY=/var/data/verigate/keys/issuer.pub
VERIGATE_GOVERNANCE_PRIVATE_KEY=/var/data/verigate/keys/governance.key
VERIGATE_GOVERNANCE_PUBLIC_KEY=/var/data/verigate/keys/governance.pub
```

The SQLite implementation creates the database's parent directory. The key-generation code also creates parent directories. Confirm that the service user can write to the mounted paths before relying on first-start key generation. Back up the disk and test restore procedures. Do not run multiple instances against this SQLite file.

## 3. Required security environment

Set these through Render's secret/environment settings, never in Git:

- `VERIGATE_API_KEYS`: a comma-separated list containing at least one `sha256:<hex-digest>` entry. The digest must be SHA-256 of the actual API key clients will send.
- `VERIGATE_REQUIRE_AUTH=1`: fail closed if API authentication is not configured.
- `VERIGATE_KEY_PASSPHRASE`: a strong, unique secret for the issuer and governance private keys.
- `VERIGATE_REQUIRE_ENCRYPTED_KEY=1`: refuse plaintext private keys.
- `VERIGATE_REQUIRE_SIGNED_INTENT=1`: disable the unsigned capability-authority path.
- `VERIGATE_REQUIRE_GOVERNED_POLICY=1`: require governed policy versions for policy changes.

Keep `VERIGATE_ENABLE_DEMO_ENDPOINTS` and `VERIGATE_ENABLE_DEMO_TAMPER` unset or false. Do not enable ungoverned attestor bootstrap in a public service. The `/demo` UI is mounted separately from the optional `/v1/demo/*` API endpoints; verify that the configured API authentication also protects the UI path as intended.

Before setting the encrypted-key requirement, verify that the current key-generation and key-loading code supports the selected passphrase and that the persistent disk contains the intended encrypted keys. Never replace existing signing keys casually: that changes the issuer identity and may invalidate prior signatures.

## 4. Pre-deployment gates

Run these against the exact commit intended for deployment:

1. Install dependencies in a clean Python environment with `pip install -r requirements.txt`. Resolve any package-resolution or build failure before deploying.
2. Run the repository's full test suite and relevant API/auth/storage tests.
3. Verify that the startup path works with the persistent paths above and encrypted issuer keys enabled.
4. Verify that demo endpoints are disabled.
5. Verify that the app can reopen its SQLite database after a process restart without losing authorization/nonce state.

**Latest CI evidence (28 Oct 2026):** the PR #14 CI run completed successfully, including dependency installation, 432 unit tests, the end-to-end demo, and API-app import. This is CI evidence only; the encrypted-key production configuration, durable restart behavior, and live hosted API have not yet been independently acceptance-tested. Repeat the checks for the exact commit selected for deployment.

Do not skip a failed check or loosen security flags just to make the service start.

## 5. Post-deployment acceptance checks

Use a newly generated test API key and test-only identity; never paste production secrets into logs or a ticket.

1. `GET /health` returns HTTP 200.
2. A protected request without a key is denied.
3. A protected request with a wrong key is denied.
4. The same request with the correct key reaches the expected authenticated route.
5. A signed action intent is verified and authorization is issued only when policy permits it.
6. An execution authorization is consumed once; a second consume attempt is denied.
7. Restart the service and confirm the database, issuer public key, governance public key, and one-time-consumption behavior remain consistent.
8. Confirm demo routes are disabled and inspect logs for leaked secrets.

A health response alone is not evidence that authorization, durable replay protection, or execution integration is working.

## 6. Current limitations

- The repository currently uses SQLite. Treat the initial service as single-instance until storage and concurrency semantics are deliberately redesigned and tested.
- This service does not itself prove a live PortalPilot-to-Verigate-to-PortalDot end-to-end flow. That requires a separately configured integration and a real acceptance test.
- Do not claim production readiness, external verification, or live integration merely because Render reports the service as healthy.
- No service has been created or deployed by this runbook.
