# Wallet Governance Outbox Operations

The transactional outbox is the durable hand-off between Verigate and the separately administered wallet-governance transparency log. The worker retries delivery; this health check reports whether accepted actions are accumulating faster than they are being acknowledged.

## Health check

Run from the Verigate application environment against the same SQLite database used by the application and outbox worker:

```sh
python scripts/wallet_governance_outbox_health.py \
  --database /var/lib/verigate/verigate.db \
  --max-pending-age-seconds 300 \
  --max-pending-count 100 \
  --max-attempts 10
```

The command writes one JSON document to stdout and returns:

- `0` — `HEALTHY`: no threshold was exceeded.
- `1` — `DEGRADED`: one threshold was exceeded.
- `2` — `UNHEALTHY`: multiple thresholds were exceeded, or the check itself failed.

Metrics include total, pending and delivered event counts; age of the oldest pending event; maximum retry count among pending events; number of installations with pending events; and the timestamp of the most recent successful delivery. Alerts are deterministic identifiers suitable for Prometheus textfile collectors, node monitoring agents, or log-based alerting.

## Suggested alert policy

- Alert immediately when `PENDING_QUEUE_TOO_LARGE` or `PENDING_EVENT_RETRY_LIMIT_EXCEEDED` appears.
- Page the on-call operator when `OLDEST_PENDING_EVENT_TOO_OLD` persists beyond the agreed service objective.
- Alert separately when the health command returns `MONITORING_CHECK_FAILED`; this means monitoring cannot establish the state of the outbox.
- Track pending count and oldest-event age as time series. A growing pending queue can indicate that the external log is down, credentials expired, TLS routing failed, or the worker stopped.
- Correlate delivery errors printed by `wallet_governance_outbox_worker.py` with reverse-proxy and log-service access/error logs. Never log bearer credentials or private signing material.

## Operational checks

1. Confirm the worker is supervised and running against the correct application database.
2. Confirm the log service is reachable through the TLS reverse proxy.
3. Confirm the worker's active bearer token is accepted by the log service.
4. Confirm the worker is provisioned with the independently distributed Ed25519 public key.
5. Confirm operators retain the latest signed checkpoint digest through a separate trusted channel for offline verification.
6. After recovery, verify pending count returns to zero and inspect the external checkpoint's entry count and digest.

The health check is a read-only snapshot. It does not retry events, change enrollment state, restart services, rotate credentials, or contact the remote log. A healthy local outbox does not prove that a separately stored trusted checkpoint digest has been distributed to verifiers. Monitoring and checkpoint pin distribution remain separate controls.
