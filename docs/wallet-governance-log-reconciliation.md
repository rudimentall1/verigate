# Wallet Governance Log Reconciliation

The reconciliation command compares the complete locally accepted wallet-governance history with the independent transparency service. It fetches the remote bundle over the authenticated HTTP transport, validates the full entry hash chain and Ed25519 checkpoint signature, and requires both the independently distributed public key and the exact latest checkpoint digest supplied by the operator.

## Run

Set the same service bearer token used by the outbox worker without placing it on the command line:

```sh
export VERIGATE_WALLET_GOVERNANCE_LOG_BEARER_TOKEN='...'
python scripts/wallet_governance_log_reconcile.py \
  --database /var/lib/verigate/verigate.db \
  --service-url https://wallet-log.example.com \
  --installation-principal 'anna-installation:<64 lowercase hex characters>' \
  --trusted-log-public-key-b64 '<independently distributed Ed25519 public key>' \
  --trusted-checkpoint-sha256 '<64 hex characters>'
```

Exit code `0` means the complete local history matches the remotely fetched chain and the checkpoint verifies against both independent pins. Exit code `2` means reconciliation failed or could not be completed. The command emits a JSON report to stdout.

## Trust and operational boundaries

- Obtain the public key and current checkpoint SHA-256 through a channel independent of the transparency service and the Verigate application database.
- Do not copy the checkpoint digest from the just-fetched HTTP response into the trusted argument. Doing so removes the independent freshness/rollback check.
- The service endpoint requires bearer authentication and returns only the requested installation principal's full bundle. The existing `/healthz` endpoint remains unauthenticated and does not disclose log data.
- Reconciliation opens the application database through SQLite `mode=ro` and `query_only`; it does not create a missing database, run application schema migrations, append events, update outbox delivery state, rotate credentials, or update trusted pins.
- The check proves that the remote bundle is the exact locally recorded accepted history and that the current checkpoint matches the operator-supplied pin. It cannot prove that the local database itself contains every action ever accepted if that database was rolled back or tampered with. Preserve independent checkpoint pins and backups.
- A checkpoint pin must be advanced only after an independently trusted process has reviewed and accepted the new checkpoint. Never auto-learn a new pin from the service response.
