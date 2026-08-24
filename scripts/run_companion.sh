#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

runtime_env="$repo_root/.runtime/companion.env"
if [[ -f "$runtime_env" ]]; then
  set -a
  # This file is owned by the service account and lets experiments switch
  # runtime profiles without rewriting the root-owned systemd unit.
  # shellcheck disable=SC1090
  source "$runtime_env"
  set +a
fi

export GEMMA_CAMERA_DEVICE="${GEMMA_CAMERA_DEVICE:-/dev/video0}"
export GEMMA_AUDIO_CAPTURE_DEVICE="${GEMMA_AUDIO_CAPTURE_DEVICE:-plughw:CARD=Device,DEV=0}"
export GEMMA_AUDIO_PLAYBACK_DEVICE="${GEMMA_AUDIO_PLAYBACK_DEVICE:-plughw:CARD=Device,DEV=0}"
export GEMMA_PLAYBACK_VOLUME="${GEMMA_PLAYBACK_VOLUME:-100}"
export GEMMA_SPEECH_MODE="${GEMMA_SPEECH_MODE:-whisper}"
export PYTHONUNBUFFERED=1

case "$GEMMA_SPEECH_MODE" in
  direct)
    # Native audio needs the multimodal scratch space that the production
    # two-slot server otherwise reserves for concurrency and prefix reuse.
    export GEMMA_PARALLEL="${GEMMA_PARALLEL:-1}"
    export GEMMA_CONTEXT_SIZE="${GEMMA_CONTEXT_SIZE:-3072}"
    export GEMMA_BATCH_SIZE="${GEMMA_BATCH_SIZE:-64}"
    export GEMMA_UBATCH_SIZE="${GEMMA_UBATCH_SIZE:-64}"
    export GEMMA_CACHE_TYPE_K="${GEMMA_CACHE_TYPE_K:-q8_0}"
    export GEMMA_CACHE_TYPE_V="${GEMMA_CACHE_TYPE_V:-q8_0}"
    # GPU projector reuse across audio and image requests currently exhausts
    # the Orin Nano's shared 8 GB memory. Keep the experimental profile safe
    # by default; callers may explicitly opt into route-only GPU experiments.
    export GEMMA_MMPROJ_OFFLOAD="${GEMMA_MMPROJ_OFFLOAD:-off}"
    export GEMMA_CAMERA_MAX_LONG_EDGE="${GEMMA_CAMERA_MAX_LONG_EDGE:-512}"
    export GEMMA_EDGE_DETAIL_MAX_LONG_EDGE="${GEMMA_EDGE_DETAIL_MAX_LONG_EDGE:-512}"
    export GEMMA_REQUEST_TIMEOUT_SECONDS="${GEMMA_REQUEST_TIMEOUT_SECONDS:-120}"
    ;;
  whisper)
    export GEMMA_PARALLEL="${GEMMA_PARALLEL:-2}"
    export GEMMA_CONTEXT_SIZE="${GEMMA_CONTEXT_SIZE:-4096}"
    export GEMMA_BATCH_SIZE="${GEMMA_BATCH_SIZE:-128}"
    export GEMMA_UBATCH_SIZE="${GEMMA_UBATCH_SIZE:-128}"
    export GEMMA_CACHE_TYPE_K="${GEMMA_CACHE_TYPE_K:-f16}"
    export GEMMA_CACHE_TYPE_V="${GEMMA_CACHE_TYPE_V:-f16}"
    export GEMMA_MMPROJ_OFFLOAD="${GEMMA_MMPROJ_OFFLOAD:-on}"
    export GEMMA_CAMERA_MAX_LONG_EDGE="${GEMMA_CAMERA_MAX_LONG_EDGE:-1024}"
    export GEMMA_EDGE_DETAIL_MAX_LONG_EDGE="${GEMMA_EDGE_DETAIL_MAX_LONG_EDGE:-1024}"
    export GEMMA_REQUEST_TIMEOUT_SECONDS="${GEMMA_REQUEST_TIMEOUT_SECONDS:-30}"
    ;;
  *)
    echo "ERROR: GEMMA_SPEECH_MODE must be direct or whisper" >&2
    exit 2
    ;;
esac

# The TTS venv intentionally reuses Ubuntu's already-verified Pillow package.
if [[ -d /usr/lib/python3/dist-packages ]]; then
  export PYTHONPATH="/usr/lib/python3/dist-packages${PYTHONPATH:+:$PYTHONPATH}"
fi

mkdir -p "$repo_root/logs" "$repo_root/captures/companion" "$repo_root/.runtime"
exec 9>"$repo_root/.runtime/companion.lock"
if ! flock -n 9; then
  echo "ERROR: another Gemma Companion session is already running" >&2
  exit 1
fi

ready=false
for _ in $(seq 1 120); do
  if [[ -e "$GEMMA_CAMERA_DEVICE" && -e /proc/asound/Device/pcm0c && -e /proc/asound/Device/pcm0p ]]; then
    ready=true
    break
  fi
  sleep 1
done
if [[ "$ready" != true ]]; then
  echo "ERROR: OBSBOT or AT-CSP1 did not become ready within 120 seconds" >&2
  exit 1
fi

python3 "$repo_root/scripts/set_volume.py" "$GEMMA_PLAYBACK_VOLUME"

if [[ "$GEMMA_SPEECH_MODE" == "direct" ]]; then
  "$repo_root/scripts/stop_whisper.sh" 9>&-
fi
"$repo_root/scripts/ensure_gemma.sh" 9>&-
if [[ "$GEMMA_SPEECH_MODE" == "whisper" ]]; then
  "$repo_root/scripts/ensure_whisper.sh" 9>&-
fi

python_bin=python3
if [[ -x "$repo_root/.venv/bin/python" ]]; then
  python_bin="$repo_root/.venv/bin/python"
fi

exec "$python_bin" "$repo_root/scripts/companion.py" "$@"
