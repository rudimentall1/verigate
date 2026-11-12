#!/usr/bin/env bash
set -Eeuo pipefail

[[ "$(id -u)" -eq 0 ]] || { echo "run this smoke test as root" >&2; exit 1; }
for cmd in systemctl systemd-analyze journalctl runuser useradd usermod openssl python3 node cp; do
  command -v "$cmd" >/dev/null || { echo "missing required command: $cmd" >&2; exit 1; }
done
if [[ "$(ps -p 1 -o comm= | tr -d '[:space:]')" != "systemd" ]] || ! systemctl show --property=Version >/dev/null 2>&1; then
  echo "[arc-signer-daemon-smoke] SKIP: no reachable systemd system manager in this runner"
  exit 0
fi

readonly REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly NODE_BIN="$(command -v node)"
readonly SIGNER_USER="verigate-arc-daemon-smoke"
readonly CLIENT_USER="verigate-arc-daemon-client"
readonly DENY_USER="verigate-arc-daemon-deny"
readonly UNIT_NAME="verigate-arc-signer-daemon-smoke.service"
readonly UNIT_FILE="/run/systemd/system/${UNIT_NAME}"
readonly SERVICE_ROOT="/opt/verigate-arc-signer-daemon-smoke"
readonly RUNTIME_DIR="/run/verigate-arc-daemon-smoke"
readonly STATE_DIR="/var/lib/verigate-arc-daemon-smoke"
readonly CONFIG_ROOT="/etc/verigate-arc-daemon-smoke"
readonly SOCKET_PATH="${RUNTIME_DIR}/signer.sock"
readonly REGISTRY="0x4D09CdD490c1Ce48BCB6DA5c1A6Bf41E2f5e853D"
readonly ISSUER="0x1111111111111111111111111111111111111111"
readonly REGISTRY_CODE="0x60006000556001600055"
readonly AGENT_PRIVATE_KEY="0x1111111111111111111111111111111111111111111111111111111111111111"
readonly TMP_DIR="$(mktemp -d)"
readonly RPC_KEY="${TMP_DIR}/rpc.key"
readonly RPC_CERT="${TMP_DIR}/rpc.crt"
readonly RPC_SCRIPT="${TMP_DIR}/mock-rpc.mjs"
readonly RPC_PORT_FILE="${TMP_DIR}/rpc.port"
readonly RPC_METHODS="${TMP_DIR}/rpc.methods"
RPC_PID=""
CREATED_USERS=0

fail() { echo "[arc-signer-daemon-smoke] ERROR: $*" >&2; exit 1; }

for user in "$SIGNER_USER" "$CLIENT_USER" "$DENY_USER"; do
  id "$user" >/dev/null 2>&1 && fail "test account already exists: $user"
  getent group "$user" >/dev/null && fail "test group already exists: $user"
done
for path in "$UNIT_FILE" "$SERVICE_ROOT" "$RUNTIME_DIR" "$STATE_DIR" "$CONFIG_ROOT"; do
  [[ ! -e "$path" && ! -L "$path" ]] || fail "test path already exists: $path"
done
[[ -d "$REPO_ROOT/node_modules/ethers" ]] || fail "ethers dependencies are not installed in the repository"

cleanup() {
  set +e
  systemctl stop "$UNIT_NAME" >/dev/null 2>&1
  rm -f "$UNIT_FILE"
  systemctl daemon-reload >/dev/null 2>&1
  if [[ -n "$RPC_PID" ]]; then kill "$RPC_PID" 2>/dev/null; wait "$RPC_PID" 2>/dev/null; fi
  rm -rf "$SERVICE_ROOT" "$RUNTIME_DIR" "$STATE_DIR" "$CONFIG_ROOT" "$TMP_DIR"
  if (( CREATED_USERS )); then
    for user in "$CLIENT_USER" "$DENY_USER" "$SIGNER_USER"; do
      userdel "$user" 2>/dev/null
      groupdel "$user" 2>/dev/null
    done
  fi
}
trap cleanup EXIT

useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin "$SIGNER_USER"
CREATED_USERS=1
useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin "$CLIENT_USER"
useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin "$DENY_USER"
usermod --append --groups "$SIGNER_USER" "$CLIENT_USER"

install -d -o root -g root -m 0711 "$CONFIG_ROOT"
install -d -o root -g root -m 0755 "$SERVICE_ROOT"
mkdir -p "$SERVICE_ROOT/integrations" "$SERVICE_ROOT/scripts"
cp -a "$REPO_ROOT/node_modules" "$SERVICE_ROOT/node_modules"
cp "$REPO_ROOT/integrations/arc-constrained-signer.mjs" "$SERVICE_ROOT/integrations/"
cp "$REPO_ROOT/integrations/arc-signer-socket.mjs" "$SERVICE_ROOT/integrations/"
cp "$REPO_ROOT/integrations/arc-ethers-signer-adapter.mjs" "$SERVICE_ROOT/integrations/"
cp "$REPO_ROOT/scripts/run_arc_signer.mjs" "$SERVICE_ROOT/scripts/"

openssl req -x509 -nodes -newkey rsa:2048 -keyout "$RPC_KEY" -out "$RPC_CERT" -subj "/CN=127.0.0.1" -days 1 -addext "subjectAltName=IP:127.0.0.1" >/dev/null 2>&1
chmod 0600 "$RPC_KEY"
cat > "$RPC_SCRIPT" <<'NODE'
import { createServer } from "node:https";
import { readFileSync, writeFileSync, appendFileSync } from "node:fs";
const [keyPath, certPath, portPath, methodsPath, code] = process.argv.slice(2);
const server = createServer({ key: readFileSync(keyPath), cert: readFileSync(certPath) }, (request, response) => {
  let raw = "";
  request.on("data", chunk => raw += chunk);
  request.on("end", () => {
    const handle = item => {
      appendFileSync(methodsPath, item.method + "\n");
      let result;
      if (item.method === "eth_chainId") result = "0x13b2";
      else if (item.method === "eth_getCode") result = code;
      else if (item.method === "eth_call") result = "0x" + "0".repeat(63) + "1";
      else if (item.method === "eth_blockNumber") result = "0x1";
      else return { jsonrpc: "2.0", id: item.id, error: { code: -32601, message: "method not implemented by signer smoke RPC" } };
      return { jsonrpc: "2.0", id: item.id, result };
    };
    try {
      const input = JSON.parse(raw);
      const output = Array.isArray(input) ? input.map(handle) : handle(input);
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(output));
    } catch (error) {
      response.writeHead(400);
      response.end(JSON.stringify({ error: error.message }));
    }
  });
});
server.listen(0, "127.0.0.1", () => writeFileSync(portPath, String(server.address().port)));
NODE
"$NODE_BIN" "$RPC_SCRIPT" "$RPC_KEY" "$RPC_CERT" "$RPC_PORT_FILE" "$RPC_METHODS" "$REGISTRY_CODE" >"${TMP_DIR}/rpc.log" 2>&1 &
RPC_PID=$!
for attempt in $(seq 1 100); do
  [[ -s "$RPC_PORT_FILE" ]] && break
  kill -0 "$RPC_PID" 2>/dev/null || fail "mock HTTPS RPC server exited during startup"
  sleep 0.1
done
[[ -s "$RPC_PORT_FILE" ]] || fail "mock HTTPS RPC server did not publish its port"
RPC_PORT="$(cat "$RPC_PORT_FILE")"

CODE_HASH="$("$NODE_BIN" --input-type=module -e 'import { keccak256 } from "ethers"; process.stdout.write(keccak256(process.argv[1]));' "$REGISTRY_CODE")"
AGENT_ADDRESS="$("$NODE_BIN" --input-type=module -e 'import { Wallet } from "ethers"; process.stdout.write(new Wallet(process.argv[1]).address);' "$AGENT_PRIVATE_KEY")"
[[ "${AGENT_ADDRESS,,}" != "${ISSUER,,}" ]] || fail "test agent address unexpectedly equals the configured issuer"
PRIVATE_KEY_FILE="${CONFIG_ROOT}/agent.key"
PUBLIC_KEY_FILE="${CONFIG_ROOT}/authorization-public.pem"
AUTH_ENV_FILE="${CONFIG_ROOT}/agent.env"
printf '%s\n' "$AGENT_PRIVATE_KEY" > "$PRIVATE_KEY_FILE"
"$NODE_BIN" --input-type=module -e 'import { generateKeyPairSync } from "node:crypto"; import { writeFileSync } from "node:fs"; const { publicKey } = generateKeyPairSync("ed25519"); writeFileSync(process.argv[1], publicKey.export({ type: "spki", format: "pem" }));' "$PUBLIC_KEY_FILE"
chown "$SIGNER_USER:$SIGNER_USER" "$PRIVATE_KEY_FILE" "$PUBLIC_KEY_FILE"
chmod 0600 "$PRIVATE_KEY_FILE" "$PUBLIC_KEY_FILE"
cat > "$AUTH_ENV_FILE" <<ENV
VERIGATE_SIGNER_ROLE=agent
VERIGATE_SIGNER_SOCKET=${SOCKET_PATH}
VERIGATE_SIGNER_JOURNAL=${STATE_DIR}/ops.jsonl
VERIGATE_SIGNER_PRIVATE_KEY_FILE=${PRIVATE_KEY_FILE}
VERIGATE_AUTH_PUBLIC_KEY_FILE=${PUBLIC_KEY_FILE}
VERIGATE_ARC_RPC_URL=https://127.0.0.1:${RPC_PORT}
VERIGATE_ARC_ISSUER_ADDRESS=${ISSUER}
VERIGATE_ARC_REGISTRY_ADDRESS=${REGISTRY}
VERIGATE_ARC_REGISTRY_CODE_HASH=${CODE_HASH}
VERIGATE_SIGNER_GAS_LIMIT=100000
VERIGATE_SIGNER_MAX_FEE_PER_GAS=100
VERIGATE_SIGNER_MAX_PRIORITY_FEE_PER_GAS=5
VERIGATE_SIGNER_MAX_NATIVE_COST=10000000
VERIGATE_SIGNER_DAILY_NATIVE_BUDGET=50000000
VERIGATE_SIGNER_CONFIRMATIONS=1
NODE_TLS_REJECT_UNAUTHORIZED=0
ENV
chown root:root "$AUTH_ENV_FILE"
chmod 0600 "$AUTH_ENV_FILE"

cat > "$UNIT_FILE" <<UNIT
[Unit]
Description=Disposable Verigate Arc signer daemon systemd smoke test
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SIGNER_USER}
Group=${SIGNER_USER}
WorkingDirectory=${SERVICE_ROOT}
EnvironmentFile=${AUTH_ENV_FILE}
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=${NODE_BIN} ${SERVICE_ROOT}/scripts/run_arc_signer.mjs
Restart=on-failure
RestartSec=1
UMask=0077
RuntimeDirectory=verigate-arc-daemon-smoke
RuntimeDirectoryMode=0750
StateDirectory=verigate-arc-daemon-smoke
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
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths=${RUNTIME_DIR} ${STATE_DIR}
UNIT

systemd-analyze verify "$UNIT_FILE"
systemctl daemon-reload
systemctl start "$UNIT_NAME"
wait_for_ready() {
  for attempt in $(seq 1 100); do
    if [[ -S "$SOCKET_PATH" ]] && journalctl -u "$UNIT_NAME" -o cat --no-pager 2>/dev/null | grep -Fq '"event":"arc_signer_ready"'; then return 0; fi
    systemctl is-active --quiet "$UNIT_NAME" || { journalctl -u "$UNIT_NAME" -o cat --no-pager >&2; fail "Arc signer daemon exited during initialization"; }
    sleep 0.1
  done
  journalctl -u "$UNIT_NAME" -o cat --no-pager >&2 || true
  fail "Arc signer daemon did not become ready"
}
assert_access() {
  if runuser -u "$DENY_USER" -- python3 -c 'import socket,sys; s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1])' "$SOCKET_PATH" >/dev/null 2>&1; then fail "unrelated user connected to daemon socket"; fi
  runuser -u "$CLIENT_USER" -- python3 -c 'import json,socket,sys; s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1]); s.sendall(json.dumps({"operation":"consume","authorization":{}}).encode()+bytes([10])); data=s.recv(4096); assert json.loads(data)["ok"] is False; s.close()' "$SOCKET_PATH"
}

wait_for_ready
[[ "$(stat -c '%U:%G:%a' "$SOCKET_PATH")" == "${SIGNER_USER}:${SIGNER_USER}:660" ]] || fail "unexpected daemon socket owner/group/mode"
[[ "$(stat -c '%U:%G:%a' "$RUNTIME_DIR")" == "${SIGNER_USER}:${SIGNER_USER}:750" ]] || fail "unexpected daemon runtime directory owner/group/mode"
MAIN_PID="$(systemctl show --property=MainPID --value "$UNIT_NAME")"
[[ "$(ps -o user= -p "$MAIN_PID" | xargs)" == "$SIGNER_USER" ]] || fail "Arc signer daemon is running under the wrong UID"
assert_access
systemctl restart "$UNIT_NAME"
wait_for_ready
assert_access
grep -Fq 'eth_getCode' "$RPC_METHODS" || fail "signer did not query pinned Registry runtime code"
grep -Fq 'eth_call' "$RPC_METHODS" || fail "signer did not verify the enabled issuer mapping"
if grep -Eq 'eth_sendRawTransaction|eth_sendTransaction' "$RPC_METHODS"; then fail "smoke test unexpectedly attempted a transaction broadcast"; fi
echo "[arc-signer-daemon-smoke] PASS: actual run_arc_signer daemon started/restarted under systemd, initialized against local mock Arc RPC, and enforced socket ACL without transaction broadcast"
