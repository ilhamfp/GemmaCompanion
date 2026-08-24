#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pid_file="$repo_root/.runtime/whisper-server.pid"

if [[ ! -f "$pid_file" ]]; then
  exit 0
fi

pid=$(cat "$pid_file")
if [[ "$pid" =~ ^[0-9]+$ ]] && [[ -r "/proc/$pid/cmdline" ]] \
  && tr '\0' ' ' <"/proc/$pid/cmdline" | grep -q 'whisper-server'; then
  kill "$pid"
  for _ in $(seq 1 30); do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.1
  done
  if kill -0 "$pid" 2>/dev/null; then
    echo "ERROR: Whisper server $pid did not stop" >&2
    exit 1
  fi
fi
rm -f "$pid_file"
echo "whisper: stopped for native-audio profile"
