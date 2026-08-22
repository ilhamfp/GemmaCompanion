#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_root="${GEMMA_RUNTIME_ROOT:-$repo_root/.runtime/ollama-jetson/lib/ollama}"
model_root="${OLLAMA_MODELS:-$repo_root/.runtime/ollama-models}"
server="$runtime_root/llama-server"
model="$model_root/blobs/sha256-3646b4b47dd1e5348ed7136d0848ef1a60b37d72c85761751351eade345acbfd"
projector="$model_root/blobs/sha256-58c1879a49af675689120e6d578097691f8a3a59b95e3ae8c1a73de86652bd76"
cuda_backend="$runtime_root/cuda_jetpack6"

for required in "$server" "$model" "$projector" "$cuda_backend/libggml-cuda.so"; do
  if [[ ! -e "$required" ]]; then
    echo "ERROR: missing Gemma runtime asset: $required" >&2
    echo "See README.md for the one-time model/runtime setup." >&2
    exit 1
  fi
done

export GGML_BACKEND_PATH="$cuda_backend/libggml-cuda.so"
export LD_LIBRARY_PATH="$runtime_root:$cuda_backend${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

exec "$server" \
  --model "$model" \
  --mmproj "$projector" \
  --host 127.0.0.1 \
  --port "${GEMMA_PORT:-11434}" \
  --no-webui \
  --ctx-size 2048 \
  --n-gpu-layers 999 \
  --device CUDA0 \
  --no-warmup \
  --load-mode mmap \
  --batch-size 128 \
  --ubatch-size 128 \
  --flash-attn on \
  --jinja \
  --reasoning off \
  --reasoning-budget 0 \
  --cache-ram 0
