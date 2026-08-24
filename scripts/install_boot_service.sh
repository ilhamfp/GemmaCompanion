#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service_source="$repo_root/deploy/gemma-companion.service"
service_target="/etc/systemd/system/gemma-companion.service"
dry_run=false

if [[ ${1:-} == "--dry-run" ]]; then
  dry_run=true
  shift
fi
if [[ $# -ne 0 ]]; then
  echo "Usage: $0 [--dry-run]" >&2
  exit 2
fi

if [[ "$dry_run" != true && ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "ERROR: one-time system service installation needs root." >&2
  echo "Run: sudo $repo_root/scripts/install_boot_service.sh" >&2
  exit 1
fi

service_user="${GEMMA_SERVICE_USER:-${SUDO_USER:-}}"
if [[ -z "$service_user" || "$service_user" == root ]]; then
  service_user="$(stat -c '%U' "$repo_root")"
fi
if [[ -z "$service_user" || "$service_user" == root ]] || ! id "$service_user" >/dev/null 2>&1; then
  echo "ERROR: could not determine a non-root service user." >&2
  echo "Set GEMMA_SERVICE_USER to the account that owns the clone." >&2
  exit 1
fi
if [[ "$repo_root" =~ [[:space:]] ]]; then
  echo "ERROR: the system service requires a clone path without whitespace: $repo_root" >&2
  exit 1
fi
service_group="$(id -gn "$service_user")"

escape_sed_replacement() {
  local value=$1
  value=${value//\\/\\\\}
  value=${value//&/\\&}
  value=${value//|/\\|}
  printf '%s' "$value"
}

rendered_service="$(mktemp)"
trap 'rm -f "$rendered_service"' EXIT
escaped_user="$(escape_sed_replacement "$service_user")"
escaped_group="$(escape_sed_replacement "$service_group")"
escaped_repo="$(escape_sed_replacement "$repo_root")"
sed \
  -e "s|^User=.*|User=$escaped_user|" \
  -e "s|^Group=.*|Group=$escaped_group|" \
  -e "s|^WorkingDirectory=.*|WorkingDirectory=$escaped_repo|" \
  -e "s|^ExecStart=.*|ExecStart=$escaped_repo/scripts/run_companion.sh|" \
  "$service_source" >"$rendered_service"

if [[ "$dry_run" == true ]]; then
  cat "$rendered_service"
  exit 0
fi

install -o root -g root -m 0644 "$rendered_service" "$service_target"
systemctl daemon-reload
systemctl enable --now gemma-companion.service
echo "service_user: $service_user"
echo "repository: $repo_root"
systemctl --no-pager --full status gemma-companion.service
