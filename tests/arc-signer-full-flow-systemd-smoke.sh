#!/usr/bin/env bash
set -Eeuo pipefail

[[ "$(id -u)" -eq 0 ]] || { echo "run this smoke test as root" >&2; exit 1; }
for cmd in systemctl systemd-analyze journalctl runuser useradd usermod openssl python3 node cp; do
  command -v "$cmd" >/dev/null || { echo "missing required command: $cmd" >&2; exit 1; }
done
if [[ "$(ps -p 1 -o comm= | tr -d '[:space:]')" != "systemd" ]] || ! systemctl show --property=Version >/dev/null 2>&1; then
  echo "[arc-signer-full-flow-smoke] SKIP: no reachable systemd system manager in this runner"
  exit 0
fi

readonly REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly NODE_BIN="$(command -v node)"
readonly ISSUER_USER="vg-flow-issuer"
readonly AGENT_USER="vg-flow-agent"
readonly ISSUER_CLIENT="vg-flow-issuer-client"
readonly AGENT_CLIENT="vg-flow-agent-client"
readonly DENY_USER="vg-flow-deny"
readonly UNIT_TEMPLATE="/run/systemd/system/vg-arc-signer-flow@.service"
readonly SERVICE_ROOT="/opt/verigate-arc-signer-flow"
readonly CONFIG_ROOT="/etc/verigate-arc-flow"
readonly KEY_ROOT="${CONFIG_ROOT}/keys"
readonly RPC_SCRIPT="${SERVICE_ROOT}/mock-rpc.mjs"
readonly RPC_KEY="$(mktemp)"
readonly RPC_CERT="$(mktemp)"
readonly RPC_PORT_FILE="$(mktemp)"
readonly RPC_METHODS="$(mktemp)"
readonly REGISTRY="0x4D09CdD490c1Ce48BCB6DA5c1A6Bf41E2f5e853D"
readonly USDC="0x3600000000000000000000000000000000000000"
readonly REGISTRY_CODE="0x60006000556001600055"
readonly ISSUER_PRIVATE_KEY="0x2222222222222222222222222222222222222222222222222222222222222222"
readonly AGENT_PRIVATE_KEY="0x1111111111111111111111111111111111111111111111111111111111111111"
readonly TMP_DIR="$(mktemp -d)"
RPC_PID=""
CREATED_USERS=0

fail() { echo "[arc-signer-full-flow-smoke] ERROR: $*" >&2; exit 1; }

for user in "$ISSUER_USER" "$AGENT_USER" "$ISSUER_CLIENT" "$AGENT_CLIENT" "$DENY_USER"; do
  id "$user" >/dev/null 2>&1 && fail "test account already exists: $user"
  getent group "$user" >/dev/null && fail "test group already exists: $user"
done
for path in "$UNIT_TEMPLATE" "$SERVICE_ROOT" "$CONFIG_ROOT" /run/verigate-arc-flow-issuer /run/verigate-arc-flow-agent /var/lib/verigate-arc-flow-issuer /var/lib/verigate-arc-flow-agent; do
  [[ ! -e "$path" && ! -L "$path" ]] || fail "test path already exists: $path"
done
[[ -d "$REPO_ROOT/node_modules/ethers" ]] || fail "ethers dependency is missing"

cleanup() {
  set +e
  systemctl stop vg-arc-signer-flow@issuer.service vg-arc-signer-flow@agent.service >/dev/null 2>&1
  rm -f "$UNIT_TEMPLATE"
  systemctl daemon-reload >/dev/null 2>&1
  if [[ -n "$RPC_PID" ]]; then kill "$RPC_PID" 2>/dev/null; wait "$RPC_PID" 2>/dev/null; fi
  rm -rf "$SERVICE_ROOT" "$CONFIG_ROOT" /run/verigate-arc-flow-issuer /run/verigate-arc-flow-agent /var/lib/verigate-arc-flow-issuer /var/lib/verigate-arc-flow-agent "$TMP_DIR"
  rm -f "$RPC_KEY" "$RPC_CERT" "$RPC_PORT_FILE" "$RPC_METHODS"
  if (( CREATED_USERS )); then
    for user in "$ISSUER_CLIENT" "$AGENT_CLIENT" "$DENY_USER" "$ISSUER_USER" "$AGENT_USER"; do
      userdel "$user" 2>/dev/null
      groupdel "$user" 2>/dev/null
    done
  fi
}
trap cleanup EXIT

useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin "$ISSUER_USER"
CREATED_USERS=1
useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin "$AGENT_USER"
useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin "$ISSUER_CLIENT"
useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin "$AGENT_CLIENT"
useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin "$DENY_USER"
usermod --append --groups "$ISSUER_USER" "$ISSUER_CLIENT"
usermod --append --groups "$AGENT_USER" "$AGENT_CLIENT"

install -d -o root -g root -m 0755 "$SERVICE_ROOT"
mkdir -p "$SERVICE_ROOT/integrations" "$SERVICE_ROOT/scripts"
cp -a "$REPO_ROOT/node_modules" "$SERVICE_ROOT/node_modules"
cp "$REPO_ROOT/integrations/arc-constrained-signer.mjs" "$SERVICE_ROOT/integrations/"
cp "$REPO_ROOT/integrations/arc-signer-socket.mjs" "$SERVICE_ROOT/integrations/"
cp "$REPO_ROOT/integrations/arc-ethers-signer-adapter.mjs" "$SERVICE_ROOT/integrations/"
cp "$REPO_ROOT/scripts/run_arc_signer.mjs" "$SERVICE_ROOT/scripts/"
install -d -o root -g root -m 0711 "$CONFIG_ROOT"
install -d -o root -g root -m 0711 "$KEY_ROOT"

ISSUER_ADDRESS="$("$NODE_BIN" --input-type=module -e 'import { Wallet } from "ethers"; process.stdout.write(new Wallet(process.argv[1]).address);' "$ISSUER_PRIVATE_KEY")"
AGENT_ADDRESS="$("$NODE_BIN" --input-type=module -e 'import { Wallet } from "ethers"; process.stdout.write(new Wallet(process.argv[1]).address);' "$AGENT_PRIVATE_KEY")"
[[ "${ISSUER_ADDRESS,,}" != "${AGENT_ADDRESS,,}" ]] || fail "issuer and agent test addresses must be distinct"

for role in issuer agent; do
  user="vg-flow-${role}"
  key="${KEY_ROOT}/${role}.key"
  auth_public="${KEY_ROOT}/${role}-authorization-public.pem"
  if [[ "$role" == issuer ]]; then private_key="$ISSUER_PRIVATE_KEY"; else private_key="$AGENT_PRIVATE_KEY"; fi
  printf '%s\n' "$private_key" > "$key"
  chown "$user:$user" "$key"
  chmod 0600 "$key"
done

openssl req -x509 -nodes -newkey rsa:2048 -keyout "$RPC_KEY" -out "$RPC_CERT" -subj "/CN=127.0.0.1" -days 1 -addext "subjectAltName=IP:127.0.0.1" >/dev/null 2>&1
chmod 0600 "$RPC_KEY"
cat > "$RPC_SCRIPT" <<'NODE'
import { createServer } from "node:https";
import { readFileSync, writeFileSync, appendFileSync } from "node:fs";
import { Transaction, keccak256 } from "ethers";
const [keyPath, certPath, portPath, methodsPath, registry, usdc, issuer, agent, registryCode] = process.argv.slice(2);
const receipts = new Map();
const transactions = new Map();
const nonces = new Map();
const blockHash = "0x" + "ab".repeat(32);
const zero32 = "0x" + "00".repeat(32);
const gasPrice = 25750000000n;
const toHex = value => "0x" + BigInt(value).toString(16);
function rpcError(id, message) { return { jsonrpc: "2.0", id, error: { code: -32000, message } }; }
function block() { return {
  hash: blockHash, parentHash: zero32, number: "0x64", timestamp: "0x672f0000",
  nonce: "0x0000000000000000", sha3Uncles: zero32, logsBloom: "0x" + "00".repeat(256),
  transactionsRoot: zero32, stateRoot: zero32, receiptsRoot: zero32, miner: "0x0000000000000000000000000000000000000000",
  difficulty: "0x0", totalDifficulty: "0x0", extraData: "0x", gasLimit: "0x1c9c380", gasUsed: "0x0",
  mixHash: zero32, baseFeePerGas: toHex(20000000000n), transactions: []
}; }
function handle(item) {
  const { id, method, params = [] } = item;
  appendFileSync(methodsPath, method + "\n");
  try {
    let result;
    if (method === "eth_chainId") result = "0x13b2";
    else if (method === "eth_blockNumber") result = "0x64";
    else if (method === "eth_getCode") result = String(params[0]).toLowerCase() === registry.toLowerCase() ? registryCode : "0x";
    else if (method === "eth_call") result = "0x" + "0".repeat(63) + "1";
    else if (method === "eth_gasPrice") result = toHex(gasPrice);
    else if (method === "eth_maxPriorityFeePerGas") result = toHex(2000000000n);
    else if (method === "eth_getBlockByNumber") result = block();
    else if (method === "eth_getTransactionCount") result = toHex(nonces.get(String(params[0]).toLowerCase()) ?? 0n);
    else if (method === "eth_estimateGas") {
      const to = String(params[0]?.to || "").toLowerCase();
      const selector = String(params[0]?.data || "").slice(0, 10).toLowerCase();
      if (to === registry.toLowerCase() && selector === "0xb267748a") result = toHex(100000n);
      else if (to === registry.toLowerCase() && selector === "0xbad56b75") result = toHex(40000n);
      else if (to === usdc.toLowerCase() && selector === "0xa9059cbb") result = toHex(55000n);
      else throw new Error("unexpected operation in eth_estimateGas");
    } else if (method === "eth_sendRawTransaction") {
      const raw = params[0];
      const tx = Transaction.from(raw);
      const from = String(tx.from || "").toLowerCase();
      const to = String(tx.to || "").toLowerCase();
      const selector = String(tx.data || "").slice(0, 10).toLowerCase();
      if (tx.chainId !== 5042n || tx.value !== 0n) throw new Error("wrong chain or non-zero native value");
      let gasUsed;
      if (selector === "0xb267748a") {
        if (from !== issuer.toLowerCase() || to !== registry.toLowerCase()) throw new Error("registration signer or destination mismatch");
        gasUsed = 94914n;
      } else if (selector === "0xbad56b75") {
        if (from !== agent.toLowerCase() || to !== registry.toLowerCase()) throw new Error("consume signer or destination mismatch");
        gasUsed = 34267n;
      } else if (selector === "0xa9059cbb") {
        if (from !== agent.toLowerCase() || to !== usdc.toLowerCase()) throw new Error("payment signer or destination mismatch");
        gasUsed = 48722n;
      } else throw new Error("unexpected transaction selector");
      const hash = keccak256(raw);
      const nonce = BigInt(tx.nonce);
      nonces.set(from, nonce + 1n);
      const txObject = { hash, from: tx.from, to: tx.to, input: tx.data, value: toHex(tx.value), nonce: toHex(nonce), chainId: toHex(tx.chainId), type: "0x2", blockNumber: "0x64", blockHash, transactionIndex: toHex(BigInt(transactions.size)) };
      transactions.set(hash.toLowerCase(), txObject);
      receipts.set(hash.toLowerCase(), {
        transactionHash: hash, transactionIndex: txObject.transactionIndex, blockHash, blockNumber: "0x64",
        from: tx.from, to: tx.to, cumulativeGasUsed: toHex(gasUsed), gasUsed: toHex(gasUsed),
        effectiveGasPrice: toHex(gasPrice), status: "0x1", type: "0x2", logs: [], logsBloom: "0x" + "00".repeat(256)
      });
      result = hash;
    } else if (method === "eth_getTransactionReceipt") result = receipts.get(String(params[0]).toLowerCase()) ?? null;
    else if (method === "eth_getTransactionByHash") result = transactions.get(String(params[0]).toLowerCase()) ?? null;
    else throw new Error("unsupported local mock RPC method: " + method);
    return { jsonrpc: "2.0", id, result };
  } catch (error) { return rpcError(id, error.message); }
}
const server = createServer({ key: readFileSync(keyPath), cert: readFileSync(certPath) }, (request, response) => {
  let raw = "";
  request.on("data", chunk => raw += chunk);
  request.on("end", () => {
    try {
      const input = JSON.parse(raw);
      const output = Array.isArray(input) ? input.map(handle) : handle(input);
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify(output));
    } catch (error) { response.writeHead(400); response.end(JSON.stringify({ error: error.message })); }
  });
});
server.listen(0, "127.0.0.1", () => writeFileSync(portPath, String(server.address().port)));
NODE
"$NODE_BIN" "$RPC_SCRIPT" "$RPC_KEY" "$RPC_CERT" "$RPC_PORT_FILE" "$RPC_METHODS" "$REGISTRY" "$USDC" "$ISSUER_ADDRESS" "$AGENT_ADDRESS" "$REGISTRY_CODE" >"${TMP_DIR}/rpc.log" 2>&1 &
RPC_PID=$!
for attempt in $(seq 1 100); do [[ -s "$RPC_PORT_FILE" ]] && break; kill -0 "$RPC_PID" 2>/dev/null || fail "mock RPC exited"; sleep 0.1; done
[[ -s "$RPC_PORT_FILE" ]] || fail "mock RPC did not start"
RPC_PORT="$(cat "$RPC_PORT_FILE")"
CODE_HASH="$("$NODE_BIN" --input-type=module -e 'import { keccak256 } from "ethers"; process.stdout.write(keccak256(process.argv[1]));' "$REGISTRY_CODE")"

"$NODE_BIN" --input-type=module -e 'import { generateKeyPairSync, sign } from "node:crypto"; import { writeFileSync } from "node:fs"; import { canonicalJson, ARC_CHAIN_ID, ARC_USDC } from process.argv[1]; import { Wallet } from "ethers"; const issuer=new Wallet(process.argv[2]); const agent=new Wallet(process.argv[3]); const recipient="0x3333333333333333333333333333333333333333"; const amount=1250000n; const data="0xa9059cbb"+recipient.slice(2).padStart(64,"0")+amount.toString(16).padStart(64,"0"); const now=Math.floor(Date.now()/1000); const payload={authorization_version:1,authorization_id:"0x"+"aa".repeat(32),issued_at:now-2,expires_at:now+240,action:{network:"arc",asset:"USDC",action_type:"payment",target:recipient,amount_exact:"1.25",metadata:{arc:{chain_id:ARC_CHAIN_ID,asset:"USDC",token_address:ARC_USDC,token_decimals:6},evm_transaction:{chain_id:ARC_CHAIN_ID,from:agent.address,to:ARC_USDC,data,value_wei:"0"}}}}; const pair=generateKeyPairSync("ed25519"); const authorization={algorithm:"Ed25519",payload,signature:sign(null,Buffer.from(canonicalJson(payload)),pair.privateKey).toString("base64")}; writeFileSync(process.argv[4],pair.publicKey.export({type:"spki",format:"pem"})); writeFileSync(process.argv[5],JSON.stringify(authorization)); writeFileSync(process.argv[6],issuer.address+"\n"+agent.address+"\n");' "file://${SERVICE_ROOT}/integrations/arc-constrained-signer.mjs" "$ISSUER_PRIVATE_KEY" "$AGENT_PRIVATE_KEY" "${TMP_DIR}/authorization-public.pem" "${TMP_DIR}/authorization.json" "${TMP_DIR}/addresses.txt"
AUTH_PUBLIC_SOURCE="${TMP_DIR}/authorization-public.pem"
AUTH_FILE="${TMP_DIR}/authorization.json"
mapfile -t ADDRESSES < "${TMP_DIR}/addresses.txt"
[[ "${ADDRESSES[0],,}" == "${ISSUER_ADDRESS,,}" && "${ADDRESSES[1],,}" == "${AGENT_ADDRESS,,}" ]] || fail "authorization fixture address mismatch"

for role in issuer agent; do
  user="vg-flow-${role}"
  key="${KEY_ROOT}/${role}.key"
  public="${KEY_ROOT}/${role}-authorization-public.pem"
  cp "$AUTH_PUBLIC_SOURCE" "$public"
  chown "$user:$user" "$public"
  chmod 0600 "$public"
done

for role in issuer agent; do
  cat > "${CONFIG_ROOT}/${role}.env" <<ENV
VERIGATE_SIGNER_ROLE=${role}
VERIGATE_SIGNER_SOCKET=/run/verigate-arc-flow-${role}/signer.sock
VERIGATE_SIGNER_JOURNAL=/var/lib/verigate-arc-flow-${role}/ops.jsonl
VERIGATE_SIGNER_PRIVATE_KEY_FILE=${KEY_ROOT}/${role}.key
VERIGATE_AUTH_PUBLIC_KEY_FILE=${KEY_ROOT}/${role}-authorization-public.pem
VERIGATE_ARC_RPC_URL=https://127.0.0.1:${RPC_PORT}
VERIGATE_ARC_ISSUER_ADDRESS=${ISSUER_ADDRESS}
VERIGATE_ARC_REGISTRY_ADDRESS=${REGISTRY}
VERIGATE_ARC_REGISTRY_CODE_HASH=${CODE_HASH}
VERIGATE_SIGNER_GAS_LIMIT=150000
VERIGATE_SIGNER_MAX_FEE_PER_GAS=50000000000
VERIGATE_SIGNER_MAX_PRIORITY_FEE_PER_GAS=5000000000
VERIGATE_SIGNER_MAX_NATIVE_COST=10000000000000000
VERIGATE_SIGNER_DAILY_NATIVE_BUDGET=100000000000000000
VERIGATE_SIGNER_CONFIRMATIONS=1
NODE_TLS_REJECT_UNAUTHORIZED=0
ENV
  chown root:root "${CONFIG_ROOT}/${role}.env"
  chmod 0600 "${CONFIG_ROOT}/${role}.env"
done

cat > "$UNIT_TEMPLATE" <<UNIT
[Unit]
Description=Disposable Verigate Arc signer full-flow systemd smoke test (%i)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=vg-flow-%i
Group=vg-flow-%i
WorkingDirectory=${SERVICE_ROOT}
EnvironmentFile=${CONFIG_ROOT}/%i.env
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=${NODE_BIN} ${SERVICE_ROOT}/scripts/run_arc_signer.mjs
Restart=on-failure
RestartSec=1
UMask=0077
RuntimeDirectory=verigate-arc-flow-%i
RuntimeDirectoryMode=0750
StateDirectory=verigate-arc-flow-%i
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
ReadWritePaths=/run/verigate-arc-flow-%i /var/lib/verigate-arc-flow-%i
UNIT

systemd-analyze verify "$UNIT_TEMPLATE"
systemctl daemon-reload
systemctl start vg-arc-signer-flow@issuer.service vg-arc-signer-flow@agent.service

wait_ready() {
  local role="$1" socket="/run/verigate-arc-flow-$1/signer.sock" unit="vg-arc-signer-flow@$1.service"
  for attempt in $(seq 1 100); do
    if [[ -S "$socket" ]] && journalctl -u "$unit" -o cat --no-pager 2>/dev/null | grep -Fq '"event":"arc_signer_ready"'; then return 0; fi
    systemctl is-active --quiet "$unit" || { journalctl -u "$unit" -o cat --no-pager >&2; fail "$unit exited before ready"; }
    sleep 0.1
  done
  fail "$unit did not become ready"
}
wait_ready issuer
wait_ready agent

request_signer() {
  local user="$1" socket="$2" operation="$3" replay="$4"
  runuser -u "$user" -- python3 -c 'import json,socket,sys; path,auth,op,replay=sys.argv[1:]; body={"operation":op,"authorization":json.load(open(auth,encoding="utf-8"))}; s=socket.socket(socket.AF_UNIX); s.settimeout(5); s.connect(path); s.sendall(json.dumps(body).encode()+bytes([10])); data=b"";\nwhile not data.endswith(bytes([10])): data+=s.recv(4096); s.close(); result=json.loads(data); assert result.get("ok") is True,result; assert result.get("replay") is (replay=="true"),result; print(json.dumps(result))' "$socket" "$AUTH_FILE" "$operation" "$replay"
}
request_rejected() {
  local user="$1" socket="$2" operation="$3" expected="$4"
  runuser -u "$user" -- python3 -c 'import json,socket,sys; path,auth,op,expected=sys.argv[1:]; body={"operation":op,"authorization":json.load(open(auth,encoding="utf-8"))}; s=socket.socket(socket.AF_UNIX); s.settimeout(5); s.connect(path); s.sendall(json.dumps(body).encode()+bytes([10])); data=b"";\nwhile not data.endswith(bytes([10])): data+=s.recv(4096); s.close(); result=json.loads(data); assert result.get("ok") is False,result; assert expected in result.get("error",""),result; print(result.get("error"))' "$socket" "$AUTH_FILE" "$operation" "$expected"
}
assert_denied() {
  local socket="$1"
  if runuser -u "$DENY_USER" -- python3 -c 'import socket,sys; s=socket.socket(socket.AF_UNIX); s.connect(sys.argv[1])' "$socket" >/dev/null 2>&1; then fail "unrelated user connected to $socket"; fi
}

ISSUER_SOCKET=/run/verigate-arc-flow-issuer/signer.sock
AGENT_SOCKET=/run/verigate-arc-flow-agent/signer.sock
assert_denied "$ISSUER_SOCKET"
assert_denied "$AGENT_SOCKET"
request_rejected "$AGENT_CLIENT" "$AGENT_SOCKET" register "agent signer cannot register"
request_rejected "$ISSUER_CLIENT" "$ISSUER_SOCKET" consume "issuer signer cannot execute"

echo "[arc-signer-full-flow-smoke] registering authorization with isolated issuer signer"
request_signer "$ISSUER_CLIENT" "$ISSUER_SOCKET" register false
echo "[arc-signer-full-flow-smoke] consuming same authorization with agent signer"
request_signer "$AGENT_CLIENT" "$AGENT_SOCKET" consume false
echo "[arc-signer-full-flow-smoke] paying exact ERC-20 USDC transfer with agent signer"
request_signer "$AGENT_CLIENT" "$AGENT_SOCKET" payment false

echo "[arc-signer-full-flow-smoke] verifying completed-operation replay does not broadcast again"
request_signer "$ISSUER_CLIENT" "$ISSUER_SOCKET" register true
request_signer "$AGENT_CLIENT" "$AGENT_SOCKET" consume true
request_signer "$AGENT_CLIENT" "$AGENT_SOCKET" payment true

[[ "$(grep -c '^eth_sendRawTransaction$' "$RPC_METHODS" || true)" == "3" ]] || fail "expected exactly three local broadcasts for register/consume/payment"
grep -Fq '"state":"complete"' /var/lib/verigate-arc-flow-issuer/ops.jsonl || fail "issuer registration was not journaled complete"
grep -Fq '"state":"complete"' /var/lib/verigate-arc-flow-agent/ops.jsonl || fail "agent operations were not journaled complete"
for role in issuer agent; do
  systemctl is-active --quiet "vg-arc-signer-flow@${role}.service" || fail "${role} signer not active"
  [[ "$(stat -c '%U:%G:%a' "/run/verigate-arc-flow-${role}/signer.sock")" == "vg-flow-${role}:vg-flow-${role}:660" ]] || fail "unexpected ${role} socket owner/group/mode"
done
echo "[arc-signer-full-flow-smoke] PASS: actual issuer and agent signer daemons under systemd completed register -> consume -> payment against local mock RPC; exact destinations/selectors/roles were checked; duplicate retries replayed journal outcomes; only three local raw transactions were accepted; no public RPC or mainnet transaction was used"
