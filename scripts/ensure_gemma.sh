#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
port="${GEMMA_PORT:-11434}"
endpoint="http://127.0.0.1:$port/props"
pid_file="$repo_root/.runtime/gemma-server.pid"
profile_file="$repo_root/.runtime/gemma-server.profile"

profile=$(printf \
  'parallel=%s\ncontext=%s\nbatch=%s\nubatch=%s\ncache_k=%s\ncache_v=%s\nmmproj_offload=%s\nport=%s\n' \
  "${GEMMA_PARALLEL:-2}" \
  "${GEMMA_CONTEXT_SIZE:-4096}" \
  "${GEMMA_BATCH_SIZE:-128}" \
  "${GEMMA_UBATCH_SIZE:-128}" \
  "${GEMMA_CACHE_TYPE_K:-f16}" \
  "${GEMMA_CACHE_TYPE_V:-f16}" \
  "${GEMMA_MMPROJ_OFFLOAD:-on}" \
  "$port")

server_ready() {
  python3 - "$endpoint" <<'PY'
import sys
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1], timeout=2) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
}

profile_matches() {
  [[ -f "$profile_file" ]] && [[ "$(cat "$profile_file")" == "$profile" ]]
}

stop_managed_server() {
  [[ -f "$pid_file" ]] || {
    echo "ERROR: a Gemma server is running with a different profile but has no managed PID" >&2
    exit 1
  }
  local pid
  pid=$(cat "$pid_file")
  if [[ "$pid" =~ ^[0-9]+$ ]] && [[ -r "/proc/$pid/cmdline" ]] \
    && tr '\0' ' ' <"/proc/$pid/cmdline" | grep -q 'llama-server'; then
    kill "$pid"
    for _ in $(seq 1 30); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.2
    done
    if kill -0 "$pid" 2>/dev/null; then
      echo "ERROR: managed Gemma server $pid did not stop" >&2
      exit 1
    fi
  else
    echo "ERROR: managed Gemma PID $pid is stale or does not identify llama-server" >&2
    exit 1
  fi
  rm -f "$pid_file" "$profile_file"
}

if server_ready; then
  if profile_matches; then
    exit 0
  fi
  echo "Gemma runtime profile changed; restarting the managed server" >&2
  stop_managed_server
fi

mkdir -p "$repo_root/logs" "$repo_root/.runtime"
nohup "$repo_root/scripts/start_gemma.sh" >"$repo_root/logs/gemma-server.log" 2>&1 &
server_pid=$!
echo "$server_pid" >"$pid_file"

for _ in $(seq 1 90); do
  if ! kill -0 "$server_pid" 2>/dev/null; then
    rm -f "$pid_file" "$profile_file"
    echo "ERROR: Gemma server exited; inspect logs/gemma-server.log" >&2
    exit 1
  fi
  if server_ready; then
    printf '%s\n' "$profile" >"$profile_file"
    exit 0
  fi
  sleep 2
done

echo "ERROR: Gemma server did not become ready within 180 seconds" >&2
exit 1
