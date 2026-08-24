#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="$repo_root/.runtime/whisper-bin-ubuntu-arm64"
source_model="$repo_root/models/ggml-tiny.en.bin"
quant_model="$repo_root/models/ggml-tiny.en-q5_1.bin"
port="${GEMMA_WHISPER_PORT:-8178}"
threads="${GEMMA_WHISPER_THREADS:-6}"
audio_context="${GEMMA_WHISPER_AUDIO_CONTEXT:-1280}"
health="http://127.0.0.1:$port/health"
pid_file="$repo_root/.runtime/whisper-server.pid"
prompt="Gemma Companion. OBSBOT camera. Audio-Technica speaker. Apple AirPods charging case. smartphone. iPhone. glasses. visual scene. speaker loudness."

server_healthy() {
  python3 - "$health" <<'PY'
import sys
import urllib.request

try:
    with urllib.request.urlopen(sys.argv[1], timeout=1) as response:
        raise SystemExit(0 if response.status == 200 else 1)
except Exception:
    raise SystemExit(1)
PY
}

if server_healthy; then
  existing_pid="$(cat "$pid_file" 2>/dev/null || true)"
  existing_command=""
  if [[ "$existing_pid" =~ ^[0-9]+$ && -r "/proc/$existing_pid/cmdline" ]]; then
    existing_command="$(tr '\0' ' ' < "/proc/$existing_pid/cmdline")"
  fi
  if [[ "$existing_command" == *"$runtime_dir/whisper-server"* \
    && "$existing_command" == *"--prompt $prompt"* \
    && "$existing_command" == *"-t $threads"* \
    && "$existing_command" == *"-ac $audio_context"* \
    && "$existing_command" == *"-nt"* ]]; then
    exit 0
  fi
  if [[ "$existing_command" != *"$runtime_dir/whisper-server"* || "$existing_command" != *"--port $port"* ]]; then
    echo "ERROR: Whisper health endpoint is occupied by an unverified process" >&2
    exit 1
  fi
  kill "$existing_pid"
  for _ in $(seq 1 50); do
    kill -0 "$existing_pid" 2>/dev/null || break
    sleep 0.1
  done
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
  -m "$quant_model" -t "$threads" -ac "$audio_context" -bo 1 -bs 1 -nf -ng -nt \
  --prompt "$prompt" \
  --host 127.0.0.1 --port "$port" \
  >"$repo_root/logs/whisper-server.log" 2>&1 &
server_pid=$!
echo "$server_pid" >"$pid_file"

for _ in $(seq 1 60); do
  if ! kill -0 "$server_pid" 2>/dev/null; then
    echo "ERROR: Whisper server exited; inspect logs/whisper-server.log" >&2
    exit 1
  fi
  if server_healthy; then
    exit 0
  fi
  sleep 0.5
done

echo "ERROR: Whisper server did not become ready within 30 seconds" >&2
exit 1
