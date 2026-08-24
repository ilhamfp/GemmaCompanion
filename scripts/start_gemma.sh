#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_root="${GEMMA_RUNTIME_ROOT:-$repo_root/.runtime/ollama-jetson/lib/ollama}"
model_root="${OLLAMA_MODELS:-$repo_root/.runtime/ollama-models}"
server="$runtime_root/llama-server"
cuda_backend="$runtime_root/cuda_jetpack6"
model_tag="${GEMMA_MODEL_TAG:-e2b-it-qat}"
manifest="$model_root/manifests/registry.ollama.ai/library/gemma4/$model_tag"

if [[ ! -f "$manifest" ]]; then
  echo "ERROR: missing Gemma model manifest: $manifest" >&2
  echo "Run scripts/bootstrap_runtime.sh or follow README.md." >&2
  exit 1
fi

mapfile -t model_assets < <(
  python3 - "$manifest" "$model_root" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
model_root = Path(sys.argv[2])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
layers = {layer["mediaType"]: layer["digest"] for layer in manifest["layers"]}
for media_type in (
    "application/vnd.ollama.image.model",
    "application/vnd.ollama.image.projector",
):
    digest = layers.get(media_type)
    if not digest:
        raise SystemExit(f"manifest lacks {media_type}")
    print(model_root / "blobs" / digest.replace(":", "-"))
PY
)

if [[ ${#model_assets[@]} -ne 2 ]]; then
  echo "ERROR: could not resolve model and projector from $manifest" >&2
  exit 1
fi
model="${model_assets[0]}"
projector="${model_assets[1]}"

for required in "$server" "$model" "$projector" "$cuda_backend/libggml-cuda.so"; do
  if [[ ! -e "$required" ]]; then
    echo "ERROR: missing Gemma runtime asset: $required" >&2
    echo "See README.md for the one-time model/runtime setup." >&2
    exit 1
  fi
done

export GGML_BACKEND_PATH="$cuda_backend/libggml-cuda.so"
export LD_LIBRARY_PATH="$runtime_root:$cuda_backend${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

case "${GEMMA_MMPROJ_OFFLOAD:-on}" in
  1|on|true|yes) mmproj_offload_arg="--mmproj-offload" ;;
  0|off|false|no) mmproj_offload_arg="--no-mmproj-offload" ;;
  *)
    echo "ERROR: GEMMA_MMPROJ_OFFLOAD must be on or off" >&2
    exit 2
    ;;
esac

exec "$server" \
  --model "$model" \
  --mmproj "$projector" \
  --host 127.0.0.1 \
  --port "${GEMMA_PORT:-11434}" \
  --no-webui \
  --ctx-size "${GEMMA_CONTEXT_SIZE:-4096}" \
  --parallel "${GEMMA_PARALLEL:-2}" \
  --cache-type-k "${GEMMA_CACHE_TYPE_K:-f16}" \
  --cache-type-v "${GEMMA_CACHE_TYPE_V:-f16}" \
  --n-gpu-layers 999 \
  --device CUDA0 \
  "$mmproj_offload_arg" \
  --no-warmup \
  --load-mode mmap \
  --batch-size "${GEMMA_BATCH_SIZE:-128}" \
  --ubatch-size "${GEMMA_UBATCH_SIZE:-128}" \
  --flash-attn on \
  --jinja \
  --skip-chat-parsing \
  --reasoning off \
  --reasoning-budget 0 \
  --cache-ram 0
