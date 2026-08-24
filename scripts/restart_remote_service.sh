#!/usr/bin/env bash
set -euo pipefail

remote_host="${GEMMA_REMOTE_HOST:-iputra@192.168.55.1}"
service="gemma-companion.service"

echo "Restarting $service on $remote_host..."
ssh \
  -o BatchMode=yes \
  -o ConnectTimeout=10 \
  -o ServerAliveInterval=15 \
  -o ServerAliveCountMax=20 \
  "$remote_host" \
  'set -eu
restart_epoch=$(/bin/date +%s)
old_pid=$(/usr/bin/systemctl show gemma-companion.service -p MainPID --value)
sudo -n /usr/bin/systemctl restart gemma-companion.service
state=$(/usr/bin/systemctl is-active gemma-companion.service)
new_pid=$(/usr/bin/systemctl show gemma-companion.service -p MainPID --value)
repo_root=$(/usr/bin/systemctl show gemma-companion.service -p WorkingDirectory --value)

printf "service: gemma-companion.service\nstate: %s\nold_pid: %s\nnew_pid: %s\n" \
  "$state" "$old_pid" "$new_pid"
test "$state" = active
case "$new_pid" in
  ""|0|*[!0-9]*)
    echo "ERROR: restarted service has no live main PID" >&2
    exit 1
    ;;
esac
if test "$old_pid" = "$new_pid"; then
  echo "ERROR: service PID did not change during restart" >&2
  exit 1
fi
if test ! -x "$repo_root/scripts/test_boot_service.sh"; then
  echo "ERROR: boot verifier is missing from service working directory: $repo_root" >&2
  exit 1
fi

GEMMA_BOOT_AFTER_EPOCH="$restart_epoch" "$repo_root/scripts/test_boot_service.sh"'
