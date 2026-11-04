#!/usr/bin/env bash
set -euo pipefail
ENV_FILE=/etc/verigate-valta/verigate.env
SERVICE=verigate-valta.service

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi
read -r -s -p 'Paste Valta vk_live_ virtual key (input hidden): ' VALTA_KEY
echo
if [[ "$VALTA_KEY" != vk_live_* ]]; then
  unset VALTA_KEY
  echo 'Invalid key prefix; expected vk_live_' >&2
  exit 1
fi
umask 077
TMP_FILE="$(mktemp /etc/verigate-valta/verigate.env.XXXXXX)"
grep -v '^VALTA_VIRTUAL_KEY=' "$ENV_FILE" > "$TMP_FILE" || true
printf 'VALTA_VIRTUAL_KEY=%s\n' "$VALTA_KEY" >> "$TMP_FILE"
unset VALTA_KEY
chmod 600 "$TMP_FILE"
mv "$TMP_FILE" "$ENV_FILE"
systemctl restart "$SERVICE"
for _ in {1..15}; do
  if systemctl is-active --quiet "$SERVICE" && curl -fsS http://127.0.0.1:8004/health >/dev/null; then
    echo 'Valta virtual key installed; Verigate Valta API is healthy.'
    exit 0
  fi
  sleep 1
done
systemctl status "$SERVICE" --no-pager -l
exit 1
