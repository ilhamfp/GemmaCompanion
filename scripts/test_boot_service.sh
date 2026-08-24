#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
service=gemma-companion.service
boot_after_epoch="${GEMMA_BOOT_AFTER_EPOCH:-0}"
boot_timeout_seconds="${GEMMA_BOOT_TIMEOUT_SECONDS:-240}"

if [[ ! "$boot_after_epoch" =~ ^[0-9]+$ ]]; then
  echo "ERROR: GEMMA_BOOT_AFTER_EPOCH must be a non-negative integer" >&2
  exit 2
fi
if [[ ! "$boot_timeout_seconds" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: GEMMA_BOOT_TIMEOUT_SECONDS must be a positive integer" >&2
  exit 2
fi

systemctl is-enabled --quiet "$service"

ready=false
for _ in $(seq 1 "$boot_timeout_seconds"); do
  systemctl is-active --quiet "$service" || {
    systemctl --no-pager --full status "$service" >&2 || true
    exit 1
  }
  latest_log=""
  while IFS= read -r candidate; do
    candidate_epoch="$(stat -c %W "$candidate" 2>/dev/null || printf '0')"
    if [[ "$candidate_epoch" == 0 ]]; then
      candidate_epoch="$(python3 - "$candidate" <<'PY'
import datetime
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    for line in handle:
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if event.get("action") == "COMPANION_START":
            try:
                timestamp = datetime.datetime.fromisoformat(
                    event["timestamp"].replace("Z", "+00:00")
                )
            except (KeyError, TypeError, ValueError):
                continue
            else:
                print(int(timestamp.timestamp()))
                break
    else:
        print(0)
PY
)"
    fi
    if (( candidate_epoch < boot_after_epoch )); then
      continue
    fi
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
  echo "ERROR: companion did not publish its grounded readiness cue within ${boot_timeout_seconds} seconds" >&2
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
