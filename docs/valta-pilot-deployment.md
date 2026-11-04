# Valta pilot deployment

This is a single-tenant pilot deployment. It is deliberately bound to loopback and is not a public multi-tenant endpoint. Keep the Valta virtual key in `/etc/verigate-valta/verigate.env`; never commit it or pass it in request bodies.

## Runtime layout

- Repository: `/opt/verigate-valta-pilot`
- Python environment: `/opt/verigate-valta-pilot/.venv`
- Environment file: `/etc/verigate-valta/verigate.env` (mode `0600`)
- SQLite database and issuer keys: `/var/lib/verigate-valta/`
- API: `127.0.0.1:8004`
- Systemd unit: `verigate-valta.service`

## Required environment

Set `VERIGATE_REQUIRE_SIGNED_INTENT=1`, `VERIGATE_POLICY`, `VERIGATE_DB`, `VERIGATE_PRIVATE_KEY`, `VERIGATE_PUBLIC_KEY`, and `VALTA_PROXY_TIMEOUT_SECONDS`. Configure `VALTA_VIRTUAL_KEY` only after minting a Valta `vk_live_...` key. The `sk_valta_...` management credential is not accepted by the proxy adapter.

For a remotely reachable deployment, configure API-key authentication and TLS before changing the loopback bind address. Do not expose this pilot as a shared multi-tenant service: per-tenant Valta virtual-key isolation is not implemented.

## Install the Valta virtual key

On the server, run:

```bash
bash /opt/verigate-valta-pilot/scripts/set-valta-virtual-key.sh
```

The script reads the key without echoing it, updates the root-only environment file, restarts the service, and checks local health. The key is not printed or placed in shell history.

## Pilot scope

The policy in `policies/valta-pilot.yaml` permits only `valta.chat_completions` for `ai_inference` at `https://valta.co/v1/chat/completions`. The adapter additionally requires an explicit completion-token limit from 1 to 256, `n=1`, non-streaming mode, and binds the exact canonical request body and Valta run ID into the signed action. Valta Cap remains the upstream spend control.
