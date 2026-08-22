#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
endpoint="http://127.0.0.1:${GEMMA_PORT:-11434}/props"

if python3 - "$endpoint" <<'PY'
import sys
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1], timeout=2) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
then
  exit 0
fi

mkdir -p "$repo_root/logs" "$repo_root/.runtime"
nohup "$repo_root/scripts/start_gemma.sh" >"$repo_root/logs/gemma-server.log" 2>&1 &
server_pid=$!
echo "$server_pid" >"$repo_root/.runtime/gemma-server.pid"

for _ in $(seq 1 90); do
  if ! kill -0 "$server_pid" 2>/dev/null; then
    echo "ERROR: Gemma server exited; inspect logs/gemma-server.log" >&2
    exit 1
  fi
  if python3 - "$endpoint" <<'PY'
import sys
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1], timeout=2) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
  then
    exit 0
  fi
  sleep 2
done

echo "ERROR: Gemma server did not become ready within 180 seconds" >&2
exit 1
