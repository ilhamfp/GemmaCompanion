#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service=gemma-companion.service

systemctl is-enabled --quiet "$service"

ready=false
for _ in $(seq 1 240); do
  systemctl is-active --quiet "$service" || {
    systemctl --no-pager --full status "$service" >&2 || true
    exit 1
  }
  latest_log=""
  while IFS= read -r candidate; do
    if grep -q '"action": "COMPANION_START"' "$candidate" \
      && grep -q '"microphone": true' "$candidate"; then
      latest_log="$candidate"
      break
    fi
  done < <(ls -t "$repo_root"/logs/companion-*.jsonl 2>/dev/null || true)
  if [[ -n "$latest_log" ]] \
    && grep -q '"action": "BOOT_OBSERVE"' "$latest_log" \
    && grep -Fq "\"response\": \"Hi, I'm Gemma!\"" "$latest_log" \
    && python3 - <<'PY'
import urllib.request
for endpoint in ("http://127.0.0.1:11434/props", "http://127.0.0.1:8178/health"):
    with urllib.request.urlopen(endpoint, timeout=2) as response:
        if response.status != 200:
            raise SystemExit(1)
PY
  then
    ready=true
    break
  fi
  sleep 1
done

if [[ "$ready" != true ]]; then
  echo "ERROR: companion did not publish its grounded readiness cue within 240 seconds" >&2
  journalctl -u "$service" -n 100 --no-pager >&2 || true
  exit 1
fi

gemma_status=$(python3 - <<'PY'
import urllib.request
with urllib.request.urlopen("http://127.0.0.1:11434/props", timeout=2) as response:
    print(response.status)
PY
)
whisper_status=$(python3 - <<'PY'
import urllib.request
with urllib.request.urlopen("http://127.0.0.1:8178/health", timeout=2) as response:
    print(response.status)
PY
)

companion_pid=$(systemctl show "$service" -p MainPID --value)
[[ "$companion_pid" =~ ^[1-9][0-9]*$ ]]
kill -0 "$companion_pid"

grep -q '"action": "COMPANION_START"' "$latest_log"

printf 'service_enabled: PASS; unit=%s\n' "$service"
printf 'service_active: PASS; main_pid=%s\n' "$companion_pid"
printf 'local_models: PASS; gemma_http=%s; whisper_http=%s\n' "$gemma_status" "$whisper_status"
printf 'continuous_session: PASS; grounded_readiness=yes; log=%s\n' "$latest_log"
echo 'result: PASS boot service owns a ready offline companion session'
