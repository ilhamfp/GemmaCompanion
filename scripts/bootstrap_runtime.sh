#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="$repo_root/.runtime"
download_dir="$runtime_dir/downloads"
ollama_dir="$runtime_dir/ollama-jetson"
model_dir="$runtime_dir/ollama-models"
ollama_version="v0.32.15"

if [[ $(uname -m) != "aarch64" ]]; then
  echo "ERROR: this bootstrap is for the Jetson aarch64 runtime" >&2
  exit 1
fi
for command in curl tar unzstd sha256sum python3; do
  command -v "$command" >/dev/null || {
    echo "ERROR: required command is missing: $command" >&2
    exit 1
  }
done
mkdir -p "$download_dir" "$ollama_dir" "$model_dir" "$repo_root/models" "$repo_root/logs"

download() {
  local url=$1 destination=$2 expected_sha=$3
  if [[ ! -f "$destination" ]]; then
    curl --fail --location --retry 3 --output "$destination" "$url"
  fi
  echo "$expected_sha  $destination" | sha256sum --check --status || {
    echo "ERROR: checksum mismatch for $destination" >&2
    exit 1
  }
}

release_base="https://github.com/ollama/ollama/releases/download/$ollama_version"
generic_archive="$download_dir/ollama-linux-arm64.tar.zst"
jetpack_archive="$download_dir/ollama-linux-arm64-jetpack6.tar.zst"
download "$release_base/ollama-linux-arm64.tar.zst" "$generic_archive" \
  c898270b1690eab0f51aa9e9197686b7b4c6a7d88b83967763818f3127e477e9
download "$release_base/ollama-linux-arm64-jetpack6.tar.zst" "$jetpack_archive" \
  344636e28d3bd31ab44caae5ac917c02cbb77b4ab692acc9ef90fc83b6c80a02

if [[ ! -x "$ollama_dir/lib/ollama/llama-server" ]]; then
  unzstd --stdout "$generic_archive" | tar -xf - -C "$ollama_dir"
  unzstd --stdout "$jetpack_archive" | tar -xf - -C "$ollama_dir"
fi

manifest="$model_dir/manifests/registry.ollama.ai/library/gemma4/e2b-it-qat"
if [[ ! -f "$manifest" ]]; then
  pull_host="127.0.0.1:11435"
  OLLAMA_MODELS="$model_dir" OLLAMA_HOST="$pull_host" \
    "$ollama_dir/bin/ollama" serve >"$repo_root/logs/ollama-pull-server.log" 2>&1 &
  pull_pid=$!
  cleanup_pull_server() {
    kill "$pull_pid" 2>/dev/null || true
    wait "$pull_pid" 2>/dev/null || true
  }
  trap cleanup_pull_server EXIT
  for _ in $(seq 1 60); do
    if OLLAMA_HOST="$pull_host" "$ollama_dir/bin/ollama" list >/dev/null 2>&1; then
      break
    fi
    kill -0 "$pull_pid" 2>/dev/null || {
      echo "ERROR: temporary Ollama pull server exited; inspect logs/ollama-pull-server.log" >&2
      exit 1
    }
    sleep 1
  done
  OLLAMA_MODELS="$model_dir" OLLAMA_HOST="$pull_host" \
    "$ollama_dir/bin/ollama" pull gemma4:e2b-it-qat
  cleanup_pull_server
  trap - EXIT
fi

whisper_archive="$download_dir/whisper-bin-ubuntu-arm64.tar.gz"
download \
  "https://github.com/ggml-org/whisper.cpp/releases/download/b4938/whisper-bin-ubuntu-arm64.tar.gz" \
  "$whisper_archive" \
  94a33318650c57cc3d9a91439e0e3f0b94ba96bacd34203a06db395cf9204e40
if [[ ! -x "$runtime_dir/whisper-bin-ubuntu-arm64/whisper-cli" ]]; then
  tar -xzf "$whisper_archive" -C "$runtime_dir"
fi

whisper_model="$repo_root/models/ggml-tiny.en.bin"
download \
  "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.en.bin" \
  "$whisper_model" \
  921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f

if ! command -v espeak-ng >/dev/null && [[ ! -x "$runtime_dir/espeak/usr/bin/espeak-ng" ]]; then
  for command in apt dpkg-deb; do
    command -v "$command" >/dev/null || {
      echo "ERROR: $command is needed for the no-sudo eSpeak fallback" >&2
      exit 1
    }
  done
  espeak_download="$download_dir/espeak"
  mkdir -p "$espeak_download"
  (
    cd "$espeak_download"
    apt download espeak-ng
  )
  espeak_package=$(find "$espeak_download" -maxdepth 1 -name 'espeak-ng_*_arm64.deb' -print -quit)
  [[ -n "$espeak_package" ]] || {
    echo "ERROR: apt did not download the arm64 espeak-ng package" >&2
    exit 1
  }
  dpkg-deb --extract "$espeak_package" "$runtime_dir/espeak"
fi

echo "runtime: ready"
echo "model: gemma4:e2b-it-qat"
echo "stt: whisper.cpp tiny.en"
echo "tts: espeak-ng fallback"
echo "next: make runtime"
