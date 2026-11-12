#!/usr/bin/env bash
set -Eeuo pipefail

[[ "$(id -u)" -eq 0 ]] || { echo "run this smoke test as root" >&2; exit 1; }

if [[ "$(ps -p 1 -o comm= | tr -d '[:space:]')" != "systemd" ]] || ! systemctl show --property=Version >/dev/null 2>&1; then
  echo "[arc-signer-systemd-smoke] SKIP: no reachable systemd system manager in this runner"
  exit 0
fi

readonly SIGNER_USER="verigate-systemd-smoke-signer"
readonly ALLOW_USER="verigate-systemd-smoke-client"
readonly DENY_USER="verigate-systemd-smoke-deny"
readonly UNIT_NAME="verigate-arc-signer-smoke.service"
readonly UNIT_FILE="/run/systemd/system/${UNIT_NAME}"
readonly RUNTIME_DIR="/run/verigate-arc-signer-smoke"
readonly STATE_DIR="/var/lib/verigate-arc-signer-smoke"
readonly SERVER_ROOT="/usr/local/lib/verigate-arc-signer-smoke"
readonly SERVER_SCRIPT="${SERVER_ROOT}/server.mjs"
readonly SOCKET_PATH="${RUNTIME_DIR}/signer.sock"
readonly NODE_BIN="$(command -v node)"
CREATED_USERS=0

fail() { echo "[arc-signer-systemd-smoke] ERROR: $*" >&2; exit 1; }

for user in "$SIGNER_USER" "$ALLOW_USER" "$DENY_USER"; do
  id "$user" >/dev/null 2>&1 && fail "test account already exists: $user"
  getent group "$user" >/dev/null && fail "test group already exists: $user"
done
for path in "$UNIT_FILE" "$RUNTIME_DIR" "$STATE_DIR" "$SERVER_ROOT"; do
  [[ ! -e "$path" && ! -L "$path" ]] || fail "test path already exists: $path"
done

cleanup() {
  set +e
  systemctl stop "$UNIT_NAME" >/dev/null 2>&1
  rm -f "$UNIT_FILE"
  systemctl daemon-reload >/dev/null 2>&1
  rm -rf "$RUNTIME_DIR" "$STATE_DIR" "$SERVER_ROOT"
  if (( CREATED_USERS )); then
    for user in "$ALLOW_USER" "$DENY_USER" "$SIGNER_USER"; do
      userdel "$user" 2>/dev/null
      groupdel "$user" 2>/dev/null
    done
  fi
}
trap cleanup EXIT

useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin "$SIGNER_USER"
useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin "$ALLOW_USER"
useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin "$DENY_USER"
CREATED_USERS=1
usermod --append --groups "$SIGNER_USER" "$ALLOW_USER"

install -d -o root -g root -m 0755 "$SERVER_ROOT"
cat > "$SERVER_SCRIPT" <<'NODE'
import { createServer } from "node:net";
import { chmodSync } from "node:fs";
const socketPath = process.argv[2];
const server = createServer(socket => socket.end("ok\n"));
server.on("error", error => { process.stderr.write(error.message + "\n"); process.exit(1); });
server.listen(socketPath, () => {
  chmodSync(socketPath, 0o660);
  process.stdout.write("READY\n");
});
process.on("SIGTERM", () => server.close(() => process.exit(0)));
NODE
chmod 0644 "$SERVER_SCRIPT"

cat > "$UNIT_FILE" <<UNIT
[Unit]
Description=Disposable Verigate Arc signer systemd runtime smoke test
After=local-fs.target

[Service]
Type=simple
User=${SIGNER_USER}
Group=${SIGNER_USER}
WorkingDirectory=/
ExecStart=${NODE_BIN} ${SERVER_SCRIPT} ${SOCKET_PATH}
Restart=on-failure
RestartSec=1
UMask=0077
RuntimeDirectory=verigate-arc-signer-smoke
RuntimeDirectoryMode=0750
StateDirectory=verigate-arc-signer-smoke
StateDirectoryMode=0700
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_UNIX
ReadWritePaths=${RUNTIME_DIR} ${STATE_DIR}
UNIT

systemd-analyze verify "$UNIT_FILE"
systemctl daemon-reload
systemctl start "$UNIT_NAME"

wait_for_socket() {
  for attempt in $(seq 1 50); do
    [[ -S "$SOCKET_PATH" ]] && return 0
    sleep 0.1
  done
  systemctl status "$UNIT_NAME" --no-pager >&2 || true
  fail "systemd service did not create its Unix socket"
}
assert_socket_permissions() {
  [[ "$(stat -c '%U:%G:%a' "$SOCKET_PATH")" == "${SIGNER_USER}:${SIGNER_USER}:660" ]] || fail "unexpected socket owner/group/mode: $(stat -c '%U:%G:%a' "$SOCKET_PATH")"
  [[ "$(stat -c '%U:%G:%a' "$RUNTIME_DIR")" == "${SIGNER_USER}:${SIGNER_USER}:750" ]] || fail "unexpected runtime directory owner/group/mode"
}
assert_access_policy() {
  if runuser -u "$DENY_USER" -- python3 -c 'import socket,sys; s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1])' "$SOCKET_PATH" >/dev/null 2>&1; then
    fail "unrelated user unexpectedly connected to the systemd-managed socket"
  fi
  runuser -u "$ALLOW_USER" -- python3 -c 'import socket,sys; s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); assert s.recv(3)==b"ok\\n"; s.close()' "$SOCKET_PATH"
}

wait_for_socket
assert_socket_permissions
assert_access_policy
systemctl is-active --quiet "$UNIT_NAME" || fail "service is not active after start"
MAIN_PID="$(systemctl show --property=MainPID --value "$UNIT_NAME")"
[[ "$MAIN_PID" =~ ^[1-9][0-9]*$ ]] || fail "systemd did not expose a running MainPID"
[[ "$(ps -o user= -p "$MAIN_PID" | xargs)" == "$SIGNER_USER" ]] || fail "signer process is running under the wrong user"

echo "[arc-signer-systemd-smoke] restarting disposable service"
systemctl restart "$UNIT_NAME"
wait_for_socket
assert_socket_permissions
assert_access_policy
systemctl is-active --quiet "$UNIT_NAME" || fail "service is not active after restart"

echo "[arc-signer-systemd-smoke] PASS: real systemd start/restart, dedicated UID, runtime directory and positive/negative socket ACL checks"
