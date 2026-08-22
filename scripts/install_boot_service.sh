#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service_source="$repo_root/deploy/gemma-companion.service"
service_target="/etc/systemd/system/gemma-companion.service"

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "ERROR: one-time system service installation needs root." >&2
  echo "Run: sudo $repo_root/scripts/install_boot_service.sh" >&2
  exit 1
fi

install -o root -g root -m 0644 "$service_source" "$service_target"
systemctl daemon-reload
systemctl enable --now gemma-companion.service
systemctl --no-pager --full status gemma-companion.service
