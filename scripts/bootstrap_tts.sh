#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_dir="$repo_root/.venv"
download_dir="$repo_root/.runtime/downloads"
model_dir="$repo_root/models"

mkdir -p "$download_dir" "$model_dir"
if [[ ! -x "$venv_dir/bin/python" ]]; then
  # Ubuntu may create the isolated interpreter before reporting that ensurepip
  # is absent. That is sufficient because pip is bootstrapped inside the venv.
  python3 -m venv "$venv_dir" || true
fi
[[ -x "$venv_dir/bin/python" ]] || {
  echo "ERROR: python3 could not create $venv_dir" >&2
  exit 1
}

if ! "$venv_dir/bin/python" -m pip --version >/dev/null 2>&1; then
  curl --fail --location --retry 3 \
    https://bootstrap.pypa.io/get-pip.py \
    --output "$download_dir/get-pip.py"
  "$venv_dir/bin/python" "$download_dir/get-pip.py"
fi

"$venv_dir/bin/python" -m pip install --upgrade pip
"$venv_dir/bin/python" -m pip install \
  numpy==2.5.2 onnxruntime==1.28.0 phonemizer==3.4.0 soundfile==0.14.0 \
  pillow==12.3.0
# espeakng-loader has no Linux aarch64 wheel. audio/tts.py supplies its two
# path lookups and uses the already-installed eSpeak NG library/data directly.
"$venv_dir/bin/python" -m pip install --no-deps kokoro-onnx==0.6.1

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

release_base="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1"
download "$release_base/kokoro-v1.0.onnx" "$model_dir/kokoro-v1.0.onnx" \
  beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a
download "$release_base/voices-v1.0.bin" "$model_dir/voices-v1.0.bin" \
  bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d

echo "tts: kokoro-onnx 0.6.1 / Kokoro-82M ready"
echo "python: $venv_dir/bin/python"
