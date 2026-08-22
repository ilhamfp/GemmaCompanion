#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="$repo_root/.runtime/whisper-bin-ubuntu-arm64"
source_model="$repo_root/models/ggml-tiny.en.bin"
quant_model="$repo_root/models/ggml-tiny.en-q5_1.bin"
port="${GEMMA_WHISPER_PORT:-8178}"
health="http://127.0.0.1:$port/health"

if python3 - "$health" <<'PY'
import sys
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1], timeout=1) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
then
  exit 0
fi

for required in "$runtime_dir/whisper-server" "$runtime_dir/whisper-quantize" "$source_model"; do
  [[ -f "$required" ]] || {
    echo "ERROR: missing Whisper runtime asset: $required" >&2
    exit 1
  }
done

if [[ ! -f "$quant_model" ]]; then
  "$runtime_dir/whisper-quantize" "$source_model" "$quant_model" q5_1
fi

mkdir -p "$repo_root/logs" "$repo_root/.runtime"
nohup "$runtime_dir/whisper-server" \
  -m "$quant_model" -t 6 -bo 1 -bs 1 -nf -ng \
  --prompt "Look left. Look right. Look up. Look down. Look center. What do you see? Volume up. Volume down." \
  --host 127.0.0.1 --port "$port" \
  >"$repo_root/logs/whisper-server.log" 2>&1 &
server_pid=$!
echo "$server_pid" >"$repo_root/.runtime/whisper-server.pid"

for _ in $(seq 1 60); do
  if ! kill -0 "$server_pid" 2>/dev/null; then
    echo "ERROR: Whisper server exited; inspect logs/whisper-server.log" >&2
    exit 1
  fi
  if python3 - "$health" <<'PY'
import sys
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1], timeout=1) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
  then
    exit 0
  fi
  sleep 0.5
done

echo "ERROR: Whisper server did not become ready within 30 seconds" >&2
exit 1
