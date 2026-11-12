#!/usr/bin/env bash
set -Eeuo pipefail

readonly UNIT_NAME="verigate-arc-signer@.service"
readonly TARGET_UNIT="/etc/systemd/system/${UNIT_NAME}"
readonly INSTALL_ROOT="/opt/verigate"
readonly CONFIG_ROOT="/etc/verigate-signer"
readonly KEY_ROOT="${CONFIG_ROOT}/keys"
readonly REGISTRY="0x4D09CdD490c1Ce48BCB6DA5c1A6Bf41E2f5e853D"
readonly REGISTRY_CODE_HASH="0x6b229c049b9ba0007c318a10759a9827b5a798a4e511611872dcd4cf3973b160"
readonly ROLES=(issuer agent)
APPLY=0
PROVISION=0

usage() {
  cat <<'USAGE'
Usage:
  sudo bash deploy/arc-signer/install.sh --provision-accounts
  sudo bash deploy/arc-signer/install.sh --check
  sudo bash deploy/arc-signer/install.sh --apply

--provision-accounts creates only the two dedicated system users/groups and
private state/config directories. It does not create/import keys.
--check is read-only and validates both role configurations and key files.
--apply installs the systemd template after a successful read-only check.
It does not enable/start services or send transactions.
USAGE
}

log() { printf '[arc-signer-install] %s\n' "$*"; }
die() { printf '[arc-signer-install] ERROR: %s\n' "$*" >&2; exit 1; }

while (($#)); do
  case "$1" in
    --check) ;;
    --apply) APPLY=1 ;;
    --provision-accounts) PROVISION=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $1" ;;
  esac
  shift
done
(( APPLY + PROVISION <= 1 )) || die "choose only one mode"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
[[ "${REPO_ROOT}" == "${INSTALL_ROOT}" ]] || die "repository must be checked out at ${INSTALL_ROOT}; found ${REPO_ROOT}"
[[ -f "${REPO_ROOT}/scripts/run_arc_signer.mjs" ]] || die "signer daemon entrypoint missing"
[[ -f "${SCRIPT_DIR}/../systemd/${UNIT_NAME}" ]] || die "systemd unit template missing"

[[ -x /usr/sbin/nologin ]] || die "/usr/sbin/nologin is required for non-login signer accounts"

for cmd in systemctl getent id install stat grep cmp groupadd useradd; do
  command -v "$cmd" >/dev/null || die "required command missing: $cmd"
done
if (( APPLY || PROVISION )); then
  [[ "$(id -u)" -eq 0 ]] || die "this mode must run as root"
fi

validate_service_account() {
  local account="$1" entry name password uid gid gecos home shell
  entry="$(getent passwd "$account")" || die "missing service account $account"
  IFS=: read -r name password uid gid gecos home shell <<< "$entry"
  [[ "$name" == "$account" && "$home" == "/nonexistent" && "$shell" == "/usr/sbin/nologin" ]] || die "$account must have home /nonexistent and shell /usr/sbin/nologin"
  [[ "$(id -gn "$account")" == "$account" ]] || die "account $account must use its matching primary group"
}

provision_accounts() {
  for role in "${ROLES[@]}"; do
    local account="verigate-signer-${role}"
    getent group "$account" >/dev/null || groupadd --system "$account"
    if ! id "$account" >/dev/null 2>&1; then
      useradd --system --gid "$account" --home-dir /nonexistent --shell /usr/sbin/nologin "$account"
    fi
    validate_service_account "$account"
    install -d -o "$account" -g "$account" -m 0700 "/var/lib/verigate-signer-${role}"
  done
  install -d -o root -g root -m 0711 "$CONFIG_ROOT"
  install -d -o root -g root -m 0711 "$KEY_ROOT"
}

if (( PROVISION )); then
  provision_accounts
  log "created/verified dedicated accounts and state/config directories"
  log "no keys, environment files, systemd units or service states were changed"
  exit 0
fi

if (( APPLY )); then
  systemctl is-active --quiet verigate-arc-signer@issuer.service && die "issuer service is active; stop it before replacing the unit" || true
  systemctl is-active --quiet verigate-arc-signer@agent.service && die "agent service is active; stop it before replacing the unit" || true
fi

validate_env() {
  local role="$1"
  local file="${CONFIG_ROOT}/${role}.env"
  local expected_key="${KEY_ROOT}/${role}.key"
  local expected_pub="${KEY_ROOT}/${role}-authorization-public.pem"
  local account="verigate-signer-${role}"
  local mode name

  id "$account" >/dev/null 2>&1 || die "missing service account $account; run --provision-accounts first"
  validate_service_account "$account"
  [[ -f "$file" && ! -L "$file" ]] || die "missing regular environment file: $file"
  [[ "$(stat -c '%U:%G' "$file")" == "root:root" ]] || die "$file must be owned by root:root"
  mode="$(stat -c '%a' "$file")"
  [[ "$mode" == "600" || "$mode" == "640" ]] || die "$file must be mode 0600 or 0640"
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" == \\#* ]] && continue
    [[ "$line" == *=* ]] || die "$file contains a malformed environment line"
    name="${line%%=*}"
    case "$name" in
      VERIGATE_SIGNER_ROLE|VERIGATE_SIGNER_SOCKET|VERIGATE_SIGNER_JOURNAL|VERIGATE_SIGNER_PRIVATE_KEY_FILE|VERIGATE_AUTH_PUBLIC_KEY_FILE|VERIGATE_ARC_RPC_URL|VERIGATE_ARC_ISSUER_ADDRESS|VERIGATE_ARC_REGISTRY_ADDRESS|VERIGATE_ARC_REGISTRY_CODE_HASH|VERIGATE_SIGNER_GAS_LIMIT|VERIGATE_SIGNER_MAX_FEE_PER_GAS|VERIGATE_SIGNER_MAX_PRIORITY_FEE_PER_GAS|VERIGATE_SIGNER_MAX_NATIVE_COST|VERIGATE_SIGNER_DAILY_NATIVE_BUDGET|VERIGATE_SIGNER_CONFIRMATIONS) ;;
      *) die "$file contains unsupported environment variable: $name" ;;
    esac
  done < "$file"
  ensure_single_var() {
    local count
    count="$(grep -c "^$1=" "$file" || true)"
    [[ "$count" == "1" ]] || die "$file must define $1 exactly once"
  }

  for name in VERIGATE_SIGNER_ROLE VERIGATE_SIGNER_SOCKET VERIGATE_SIGNER_JOURNAL VERIGATE_SIGNER_PRIVATE_KEY_FILE VERIGATE_AUTH_PUBLIC_KEY_FILE VERIGATE_ARC_RPC_URL VERIGATE_ARC_ISSUER_ADDRESS VERIGATE_ARC_REGISTRY_ADDRESS VERIGATE_ARC_REGISTRY_CODE_HASH VERIGATE_SIGNER_GAS_LIMIT VERIGATE_SIGNER_MAX_FEE_PER_GAS VERIGATE_SIGNER_MAX_PRIORITY_FEE_PER_GAS VERIGATE_SIGNER_MAX_NATIVE_COST VERIGATE_SIGNER_DAILY_NATIVE_BUDGET VERIGATE_SIGNER_CONFIRMATIONS; do
    ensure_single_var "$name"
  done
  grep -Eq '(^|_)PRIVATE_KEY=' "$file" && die "$file must not contain private-key material or private-key environment variables"
  grep -Fqx "VERIGATE_SIGNER_ROLE=${role}" "$file" || die "$file has incorrect signer role"
  grep -Fqx "VERIGATE_SIGNER_SOCKET=/run/verigate-signer-${role}/signer.sock" "$file" || die "$file has incorrect socket path"
  grep -Fqx "VERIGATE_SIGNER_JOURNAL=/var/lib/verigate-signer-${role}/ops.jsonl" "$file" || die "$file has incorrect journal path"
  grep -Fqx "VERIGATE_SIGNER_PRIVATE_KEY_FILE=${expected_key}" "$file" || die "$file has incorrect private key path"
  grep -Fqx "VERIGATE_AUTH_PUBLIC_KEY_FILE=${expected_pub}" "$file" || die "$file has incorrect authorization public key path"
  grep -Fqx "VERIGATE_ARC_REGISTRY_ADDRESS=${REGISTRY}" "$file" || die "$file has incorrect pinned Registry address"
  grep -Fqx "VERIGATE_ARC_REGISTRY_CODE_HASH=${REGISTRY_CODE_HASH}" "$file" || die "$file has incorrect pinned Registry code hash"

  for name in VERIGATE_ARC_RPC_URL VERIGATE_ARC_ISSUER_ADDRESS VERIGATE_SIGNER_GAS_LIMIT VERIGATE_SIGNER_MAX_FEE_PER_GAS VERIGATE_SIGNER_MAX_PRIORITY_FEE_PER_GAS VERIGATE_SIGNER_MAX_NATIVE_COST VERIGATE_SIGNER_DAILY_NATIVE_BUDGET VERIGATE_SIGNER_CONFIRMATIONS; do
    grep -Eq "^${name}=.+$" "$file" || die "$file is missing $name"
  done
  for name in VERIGATE_SIGNER_GAS_LIMIT VERIGATE_SIGNER_MAX_FEE_PER_GAS VERIGATE_SIGNER_MAX_PRIORITY_FEE_PER_GAS VERIGATE_SIGNER_MAX_NATIVE_COST VERIGATE_SIGNER_DAILY_NATIVE_BUDGET VERIGATE_SIGNER_CONFIRMATIONS; do
    grep -Eq "^${name}=[1-9][0-9]*$" "$file" || die "$file has invalid positive integer $name"
  done
  grep -Eq '^VERIGATE_ARC_RPC_URL=https://[^ ]+$' "$file" || die "$file must use an HTTPS Arc RPC URL"
  grep -Eq '^VERIGATE_ARC_ISSUER_ADDRESS=0x[0-9a-fA-F]{40}$' "$file" || die "$file has an invalid 20-byte issuer address"

  [[ -f "$expected_key" && ! -L "$expected_key" ]] || die "missing private key file: $expected_key (installer never creates keys)"
  [[ -f "$expected_pub" && ! -L "$expected_pub" ]] || die "missing authorization public key file: $expected_pub"
  [[ "$(stat -c '%U:%a' "$expected_key")" == "${account}:600" ]] || die "$expected_key must be owned by $account and mode 0600"
  [[ "$(stat -c '%U:%a' "$expected_pub")" == "${account}:600" ]] || die "$expected_pub must be owned by $account and mode 0600"
}

for role in "${ROLES[@]}"; do
  validate_env "$role"
done
log "preflight passed: both roles have root-owned configuration, distinct key files, pinned Registry and numeric fee limits"

if (( ! APPLY )); then
  log "read-only mode; no system changes made"
  exit 0
fi

if [[ -e "$TARGET_UNIT" || -L "$TARGET_UNIT" ]]; then
  [[ -f "$TARGET_UNIT" && ! -L "$TARGET_UNIT" ]] || die "existing unit path is not a regular file"
  cmp -s "$TARGET_UNIT" "${SCRIPT_DIR}/../systemd/${UNIT_NAME}" || die "existing unit differs from the reviewed template; inspect it manually before replacement"
else
  install -o root -g root -m 0644 "${SCRIPT_DIR}/../systemd/${UNIT_NAME}" "$TARGET_UNIT"
fi
systemctl daemon-reload
log "installed unit template and reloaded systemd"
log "units were NOT enabled or started; keys/config were NOT created or changed"
log "agent runtime socket group membership must be reviewed and provisioned separately"
