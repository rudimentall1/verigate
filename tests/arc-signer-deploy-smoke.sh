#!/usr/bin/env bash
set -Eeuo pipefail

[[ "$(id -u)" -eq 0 ]] || { echo "run this smoke test as root" >&2; exit 1; }
[[ -x /usr/sbin/nologin ]] || { echo "missing /usr/sbin/nologin" >&2; exit 1; }
for cmd in runuser useradd usermod python3; do command -v "$cmd" >/dev/null || { echo "missing required command: $cmd" >&2; exit 1; }; done

readonly REPO_SOURCE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly UNIT_FILE="/etc/systemd/system/verigate-arc-signer@.service"
readonly CONFIG_ROOT="/etc/verigate-signer"
readonly ROLES=(issuer agent)
readonly SOCKET_ALLOW_USER="verigate-agent-client-smoke"
readonly SOCKET_DENY_USER="verigate-unrelated-client-smoke"
readonly SOCKET_ACL_ROOT="/var/tmp/verigate-arc-signer-acl-$BASHPID"
readonly TMP_DIR="$(mktemp -d)"
readonly SYSTEMCTL_LOG="${TMP_DIR}/systemctl.log"
SOCKET_SERVER_PID=""
CREATED_ACCOUNTS=0
CREATED_LINK=0

fail() { echo "[arc-signer-smoke] ERROR: $*" >&2; exit 1; }
log() { echo "[arc-signer-smoke] $*"; }

for role in "${ROLES[@]}"; do
  account="verigate-signer-${role}"
  id "$account" >/dev/null 2>&1 && fail "test account already exists: $account"
  getent group "$account" >/dev/null && fail "test group already exists: $account"
  [[ ! -e "/var/lib/verigate-signer-${role}" && ! -L "/var/lib/verigate-signer-${role}" ]] || fail "state directory already exists for $role"
done
for client in "$SOCKET_ALLOW_USER" "$SOCKET_DENY_USER"; do
  id "$client" >/dev/null 2>&1 && fail "socket ACL test account already exists: $client"
  getent group "$client" >/dev/null && fail "socket ACL test group already exists: $client"
done
[[ ! -e "$SOCKET_ACL_ROOT" && ! -L "$SOCKET_ACL_ROOT" ]] || fail "socket ACL test path already exists"
[[ ! -e "$CONFIG_ROOT" && ! -L "$CONFIG_ROOT" ]] || fail "$CONFIG_ROOT already exists"
[[ ! -e /opt/verigate && ! -L /opt/verigate ]] || fail "/opt/verigate already exists"
[[ ! -e "$UNIT_FILE" && ! -L "$UNIT_FILE" ]] || fail "$UNIT_FILE already exists"

cleanup() {
  set +e
  rm -f "$UNIT_FILE"
  if [[ -n "$SOCKET_SERVER_PID" ]]; then kill "$SOCKET_SERVER_PID" 2>/dev/null; wait "$SOCKET_SERVER_PID" 2>/dev/null; fi
  rm -rf "$SOCKET_ACL_ROOT"
  for client in "$SOCKET_ALLOW_USER" "$SOCKET_DENY_USER"; do
    userdel "$client" 2>/dev/null
    groupdel "$client" 2>/dev/null
  done
  for role in "${ROLES[@]}"; do
    account="verigate-signer-${role}"
    userdel "$account" 2>/dev/null
    groupdel "$account" 2>/dev/null
    rm -rf "/var/lib/verigate-signer-${role}"
  done
  rm -rf "$CONFIG_ROOT"
  if (( CREATED_LINK )); then rm -f /opt/verigate; fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

mkdir -p /opt
ln -s "$REPO_SOURCE" /opt/verigate
CREATED_LINK=1

mkdir -p "${TMP_DIR}/fakebin"
cat > "${TMP_DIR}/fakebin/systemctl" <<'SYSTEMCTL'
#!/bin/sh
printf '%s\n' "$*" >> "$SYSTEMCTL_LOG"
case "$1" in
  is-active|is-enabled) exit 1 ;;
  daemon-reload) exit 0 ;;
  *) exit 0 ;;
esac
SYSTEMCTL
chmod 0755 "${TMP_DIR}/fakebin/systemctl"
export SYSTEMCTL_LOG
export PATH="${TMP_DIR}/fakebin:$PATH"

log "provisioning disposable system users and directories"
bash /opt/verigate/deploy/arc-signer/install.sh --provision-accounts
CREATED_ACCOUNTS=1

log "testing Unix socket ACL: supplementary signer group can connect; unrelated user is denied"
useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin "$SOCKET_ALLOW_USER"
useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin "$SOCKET_DENY_USER"
usermod --append --groups verigate-signer-agent "$SOCKET_ALLOW_USER"
install -d -o root -g root -m 0755 "$SOCKET_ACL_ROOT"
install -d -o verigate-signer-agent -g verigate-signer-agent -m 0750 "$SOCKET_ACL_ROOT/runtime"
SOCKET_TEST_PATH="$SOCKET_ACL_ROOT/runtime/signer.sock"
runuser -u verigate-signer-agent -- python3 -c 'import os,socket,sys; s=socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); os.chmod(sys.argv[1],0o660); s.listen(1); c,_=s.accept(); c.sendall(b"ok"); c.close(); s.close()' "$SOCKET_TEST_PATH" >"${TMP_DIR}/socket-server.log" 2>&1 &
SOCKET_SERVER_PID=$!
for attempt in $(seq 1 50); do
  [[ -S "$SOCKET_TEST_PATH" ]] && break
  kill -0 "$SOCKET_SERVER_PID" 2>/dev/null || fail "test signer could not create its Unix socket"
  sleep 0.1
done
[[ -S "$SOCKET_TEST_PATH" ]] || fail "test signer socket did not appear"
[[ "$(stat -c '%U:%G:%a' "$SOCKET_TEST_PATH")" == "verigate-signer-agent:verigate-signer-agent:660" ]] || fail "unexpected signer socket owner/group/mode"
if runuser -u "$SOCKET_DENY_USER" -- python3 -c 'import socket,sys; s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1])' "$SOCKET_TEST_PATH" >/dev/null 2>&1; then
  fail "unrelated user unexpectedly connected to signer socket"
fi
runuser -u "$SOCKET_ALLOW_USER" -- python3 -c 'import socket,sys; s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); assert s.recv(2)==b"ok"; s.close()' "$SOCKET_TEST_PATH"
wait "$SOCKET_SERVER_PID"
SOCKET_SERVER_PID=""

for role in "${ROLES[@]}"; do
  account="verigate-signer-${role}"
  key="/etc/verigate-signer/keys/${role}.key"
  pub="/etc/verigate-signer/keys/${role}-authorization-public.pem"
  printf '0x%s\n' "$(printf '11%.0s' {1..32})" > "$key"
  printf 'test-only-public-key\n' > "$pub"
  chown "$account:$account" "$key" "$pub"
  chmod 0600 "$key" "$pub"

  sed \
    -e 's|https://REPLACE_WITH_TRUSTED_ARC_MAINNET_RPC|https://rpc.invalid|' \
    -e 's|0xREPLACE_WITH_ENABLED_REGISTRY_ISSUER|0x1111111111111111111111111111111111111111|' \
    -e 's|VERIGATE_SIGNER_GAS_LIMIT=REPLACE_WITH_MEASURED_POSITIVE_INTEGER|VERIGATE_SIGNER_GAS_LIMIT=100000|' \
    -e 's|VERIGATE_SIGNER_MAX_FEE_PER_GAS=REPLACE_WITH_MEASURED_POSITIVE_INTEGER|VERIGATE_SIGNER_MAX_FEE_PER_GAS=100|' \
    -e 's|VERIGATE_SIGNER_MAX_PRIORITY_FEE_PER_GAS=REPLACE_WITH_MEASURED_POSITIVE_INTEGER|VERIGATE_SIGNER_MAX_PRIORITY_FEE_PER_GAS=5|' \
    -e 's|VERIGATE_SIGNER_MAX_NATIVE_COST=REPLACE_WITH_REVIEWED_NATIVE_USDC_18_CEILING|VERIGATE_SIGNER_MAX_NATIVE_COST=10000000|' \
    -e 's|VERIGATE_SIGNER_DAILY_NATIVE_BUDGET=REPLACE_WITH_REVIEWED_NATIVE_USDC_18_BUDGET|VERIGATE_SIGNER_DAILY_NATIVE_BUDGET=50000000|' \
    "/opt/verigate/deploy/arc-signer/${role}.env.example" > "/etc/verigate-signer/${role}.env"
  chown root:root "/etc/verigate-signer/${role}.env"
  chmod 0640 "/etc/verigate-signer/${role}.env"

  printf '{"smoke_test":true}\n' > "/var/lib/verigate-signer-${role}/ops.jsonl"
  chown "$account:$account" "/var/lib/verigate-signer-${role}/ops.jsonl"
  chmod 0600 "/var/lib/verigate-signer-${role}/ops.jsonl"
done

log "running read-only installer preflight"
bash /opt/verigate/deploy/arc-signer/install.sh --check
log "installing unit without enabling or starting services"
bash /opt/verigate/deploy/arc-signer/install.sh --apply
[[ -f "$UNIT_FILE" ]] || fail "unit template was not installed"
cmp -s "$UNIT_FILE" /opt/verigate/deploy/systemd/verigate-arc-signer@.service || fail "installed unit differs from repository template"
command -v systemd-analyze >/dev/null || fail "systemd-analyze is required for unit validation"
systemd-analyze verify "$UNIT_FILE"
log "systemd-analyze verified the installed unit template"

log "running rollback preflight and rollback"
bash /opt/verigate/deploy/arc-signer/rollback.sh --check
bash /opt/verigate/deploy/arc-signer/rollback.sh --apply
[[ ! -e "$UNIT_FILE" && ! -L "$UNIT_FILE" ]] || fail "rollback did not remove signer unit template"

for role in "${ROLES[@]}"; do
  [[ -f "/etc/verigate-signer/${role}.env" ]] || fail "rollback removed ${role} environment file"
  [[ -f "/etc/verigate-signer/keys/${role}.key" ]] || fail "rollback removed ${role} private key file"
  [[ -f "/var/lib/verigate-signer-${role}/ops.jsonl" ]] || fail "rollback removed ${role} journal"
done

if grep -Eq '^(start|enable|stop|disable)( |$)' "$SYSTEMCTL_LOG"; then
  fail "smoke test unexpectedly started, enabled, stopped or disabled a service"
fi
log "PASS: account provisioning, config/key validation, unit install, non-start behavior and non-destructive rollback"
