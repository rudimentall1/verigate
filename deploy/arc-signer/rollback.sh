#!/usr/bin/env bash
set -Eeuo pipefail

readonly UNIT_FILE="/etc/systemd/system/verigate-arc-signer@.service"
readonly REPO_UNIT="/opt/verigate/deploy/systemd/verigate-arc-signer@.service"
readonly ROLES=(issuer agent)
APPLY=0

usage() {
  cat <<'USAGE'
Usage: sudo deploy/arc-signer/rollback.sh [--check] [--apply]

Default is read-only. --apply stops/disables only the two Verigate Arc signer
units, removes only the installed signer unit template, and reloads systemd.
It deliberately preserves users, groups, keys, environment files, journals,
logs and all unrelated services.
USAGE
}

log() { printf '[arc-signer-rollback] %s\n' "$*"; }
die() { printf '[arc-signer-rollback] ERROR: %s\n' "$*" >&2; exit 1; }

while (($#)); do
  case "$1" in
    --check) ;;
    --apply) APPLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $1" ;;
  esac
  shift
done

command -v systemctl >/dev/null || die "systemctl is required"
command -v cmp >/dev/null || die "cmp is required"
if (( APPLY )); then [[ "$(id -u)" -eq 0 ]] || die "--apply must run as root"; fi

for role in "${ROLES[@]}"; do
  unit="verigate-arc-signer@${role}.service"
  if systemctl is-active --quiet "$unit"; then log "would stop active unit: $unit"; else log "unit not active: $unit"; fi
  if systemctl is-enabled --quiet "$unit"; then log "unit is enabled: $unit"; else log "unit not enabled: $unit"; fi
done

if [[ -e "$UNIT_FILE" || -L "$UNIT_FILE" ]]; then
  [[ -f "$UNIT_FILE" && ! -L "$UNIT_FILE" ]] || die "unit path is not a regular file: $UNIT_FILE"
  [[ -f "$REPO_UNIT" ]] || die "reviewed repository unit template missing: $REPO_UNIT"
  cmp -s "$UNIT_FILE" "$REPO_UNIT" || die "installed unit differs from the reviewed template; inspect it manually and do not remove it automatically"
  log "would remove: $UNIT_FILE"
else
  log "unit template is already absent"
fi

if (( ! APPLY )); then
  log "read-only mode; no system changes made. Re-run with --apply after reviewing the impact."
  exit 0
fi

for role in "${ROLES[@]}"; do
  unit="verigate-arc-signer@${role}.service"
  if systemctl is-active --quiet "$unit"; then systemctl stop "$unit"; fi
  if systemctl is-enabled --quiet "$unit"; then systemctl disable "$unit"; fi
done

rm -f -- "$UNIT_FILE"
systemctl daemon-reload
log "signer units stopped/disabled and unit template removed"
log "preserved: signer users/groups, key files, environment files, journals, logs and unrelated services"
