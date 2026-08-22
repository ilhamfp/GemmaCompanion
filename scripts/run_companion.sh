#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

export GEMMA_CAMERA_DEVICE="${GEMMA_CAMERA_DEVICE:-/dev/video0}"
export GEMMA_AUDIO_CAPTURE_DEVICE="${GEMMA_AUDIO_CAPTURE_DEVICE:-plughw:CARD=Device,DEV=0}"
export GEMMA_AUDIO_PLAYBACK_DEVICE="${GEMMA_AUDIO_PLAYBACK_DEVICE:-plughw:CARD=Device,DEV=0}"
export GEMMA_PLAYBACK_VOLUME="${GEMMA_PLAYBACK_VOLUME:-85}"
export PYTHONUNBUFFERED=1

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

"$repo_root/scripts/ensure_gemma.sh"
"$repo_root/scripts/ensure_whisper.sh"

python_bin=python3
if [[ -x "$repo_root/.venv/bin/python" ]]; then
  python_bin="$repo_root/.venv/bin/python"
fi

exec "$python_bin" "$repo_root/scripts/companion.py" "$@"
