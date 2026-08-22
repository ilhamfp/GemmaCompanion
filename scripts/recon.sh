#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

if ! command -v arecord >/dev/null 2>&1 || ! command -v aplay >/dev/null 2>&1; then
  echo "ERROR: ALSA arecord/aplay tools are required for audio recon" >&2
  exit 1
fi

inventory_file="$(mktemp)"
trap 'rm -f "$inventory_file"' EXIT

query_v4l2_caps() {
  python3 - "$1" <<'PY'
import fcntl
import os
import struct
import sys

node = sys.argv[1]
querycap = 0x80685600
video_capture = 0x00000001
video_capture_mplane = 0x00001000
device_caps_flag = 0x80000000
buf = bytearray(104)
try:
    fd = os.open(node, os.O_RDWR | os.O_NONBLOCK)
    fcntl.ioctl(fd, querycap, buf, True)
finally:
    if "fd" in locals():
        os.close(fd)
driver, card, bus, version, capabilities, device_caps, *_ = struct.unpack("=16s32s32sIII3I", buf)
effective = device_caps if capabilities & device_caps_flag else capabilities
is_capture = bool(effective & (video_capture | video_capture_mplane))
print(f"card={card.split(bytes([0]), 1)[0].decode(errors='replace')}")
print(f"capabilities=0x{capabilities:08x} device_caps=0x{device_caps:08x}")
print(f"video_capture={'yes' if is_capture else 'no'}")
raise SystemExit(0 if is_capture else 1)
PY
}

query_v4l2_ptz() {
  python3 - "$1" <<'PY'
import errno
import fcntl
import os
import struct
import sys

node = sys.argv[1]
queryctrl = 0xC0445624
camera_class_base = 0x009A0900
controls = {
    "pan_relative": camera_class_base + 4,
    "tilt_relative": camera_class_base + 5,
    "pan_reset": camera_class_base + 6,
    "tilt_reset": camera_class_base + 7,
    "pan_absolute": camera_class_base + 8,
    "tilt_absolute": camera_class_base + 9,
}
found = 0
fd = os.open(node, os.O_RDWR | os.O_NONBLOCK)
try:
    for expected_name, control_id in controls.items():
        buf = bytearray(struct.pack("=II32siiiiI2I", control_id, 0, bytes(32), 0, 0, 0, 0, 0, 0, 0))
        try:
            fcntl.ioctl(fd, queryctrl, buf, True)
        except OSError as exc:
            if exc.errno == errno.EINVAL:
                continue
            raise
        _, _, raw_name, minimum, maximum, step, default, flags, _, _ = struct.unpack("=II32siiiiI2I", buf)
        name = raw_name.split(bytes([0]), 1)[0].decode(errors="replace") or expected_name
        print(f"{name}: id=0x{control_id:08x} min={minimum} max={maximum} step={step} default={default} flags=0x{flags:08x}")
        found += 1
finally:
    os.close(fd)
raise SystemExit(0 if found else 1)
PY
}

find_audio_technica_card() {
  local card_path device_path probe vendor product
  for card_path in /sys/class/sound/card[0-9]*; do
    [[ -e "$card_path" ]] || continue
    device_path="$(readlink -f "$card_path/device")"
    probe="$device_path"
    while [[ "$probe" != "/" && "$probe" != "." ]]; do
      vendor="$(cat "$probe/idVendor" 2>/dev/null || true)"
      product="$(cat "$probe/idProduct" 2>/dev/null || true)"
      if [[ "$vendor" == "0909" && "$product" == "005b" ]]; then
        basename "$card_path" | sed 's/^card//'
        return 0
      fi
      probe="$(dirname "$probe")"
    done
  done
  return 1
}

{
  echo '$ hostname && id && uname -a && cat /etc/nv_tegra_release'
  hostname
  id
  uname -a
  cat /etc/nv_tegra_release

  echo '$ free -h && df -h / && nproc'
  free -h
  df -h /
  nproc

  echo '$ nvidia-smi; ls /usr/local/cuda*; dpkg NVIDIA/CUDA/TensorRT packages'
  nvidia-smi 2>/dev/null || true
  ls -ld /usr/local/cuda* 2>/dev/null || true
  dpkg -l 2>/dev/null | grep -i -E 'nvidia-jetpack|cuda-toolkit|tensorrt' | head -20 || true

  echo '$ python3 --version && pip3 --version'
  python3 --version
  pip3 --version 2>/dev/null || true

  echo '$ command -v v4l2-ctl ffmpeg ollama arecord aplay gst-launch-1.0 docker'
  for binary in v4l2-ctl ffmpeg ollama arecord aplay gst-launch-1.0 docker; do
    command -v "$binary" 2>/dev/null || true
  done

  echo '$ V4L2 device inventory'
  if command -v v4l2-ctl >/dev/null 2>&1; then
    v4l2-ctl --list-devices
  else
    echo 'v4l2-ctl: not installed; using sysfs and direct V4L2 ioctls'
    for name_path in /sys/class/video4linux/video*/name; do
      [[ -r "$name_path" ]] || continue
      echo "$(cat "$name_path")"
      echo "  /dev/$(basename "$(dirname "$name_path")")"
    done
  fi

  while IFS= read -r video_node; do
    [[ -n "$video_node" ]] || continue
    if command -v v4l2-ctl >/dev/null 2>&1; then
      echo "$ v4l2-ctl -d $video_node --list-ctrls-menus"
      v4l2-ctl -d "$video_node" --list-ctrls-menus 2>&1 || true
    else
      echo "$ direct V4L2 query for $video_node"
      query_v4l2_caps "$video_node" 2>&1 || true
      query_v4l2_ptz "$video_node" 2>&1 || echo 'pan/tilt controls: none exposed'
    fi
  done < <(find /dev -maxdepth 1 -type c -name 'video*' -print | sort -V)

  echo '$ arecord -l && aplay -l'
  arecord -l
  aplay -l

  echo '$ lsusb'
  lsusb
} >"$inventory_file" 2>&1

obsbot_nodes="$({
  for name_path in /sys/class/video4linux/video*/name; do
    [[ -r "$name_path" ]] || continue
    if grep -qi obsbot "$name_path"; then
      echo "/dev/$(basename "$(dirname "$name_path")")"
    fi
  done
} | paste -sd, -)"

capture_node=""
IFS=',' read -r -a obsbot_node_array <<<"$obsbot_nodes"
for video_node in "${obsbot_node_array[@]}"; do
  if command -v v4l2-ctl >/dev/null 2>&1 && v4l2-ctl -d "$video_node" --all 2>/dev/null | grep -q 'Video Capture'; then
    capture_node="$video_node"
    break
  elif ! command -v v4l2-ctl >/dev/null 2>&1 && query_v4l2_caps "$video_node" >/dev/null 2>&1; then
    capture_node="$video_node"
    break
  fi
done

ptz_controls="none"
for video_node in "${obsbot_node_array[@]}"; do
  if command -v v4l2-ctl >/dev/null 2>&1; then
    controls="$(v4l2-ctl -d "$video_node" --list-ctrls 2>/dev/null | grep -E 'pan_|tilt_' | sed 's/^[[:space:]]*//' || true)"
  else
    controls="$(query_v4l2_ptz "$video_node" 2>/dev/null || true)"
  fi
  if [[ -n "$controls" ]]; then
    ptz_controls="$video_node: $(tr '\n' ';' <<<"$controls" | sed 's/;$//')"
    break
  fi
done

capture_card="$(find_audio_technica_card || true)"
playback_card="$capture_card"

cuda_summary="not detected"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi 2>/dev/null | grep -q 'CUDA Version:'; then
  cuda_summary="driver API $(nvidia-smi 2>/dev/null | sed -n 's/.*CUDA Version: \([^ ]*\).*/\1/p' | head -1) (nvidia-l4t-cuda installed)"
elif command -v nvcc >/dev/null 2>&1; then
  cuda_summary="$(nvcc --version | awk '/release/{print "nvcc " $0}' | sed 's/^[[:space:]]*//')"
elif [[ -f /usr/local/cuda/version.json ]]; then
  cuda_summary="$(tr -d '\n' </usr/local/cuda/version.json)"
elif compgen -G '/usr/local/cuda*' >/dev/null; then
  cuda_summary="present at $(ls -d /usr/local/cuda* | paste -sd, -)"
fi

python_summary="$(python3 --version 2>&1)"
available_ram="$(free -h | awk '/^Mem:/{print $7}')"
available_disk="$(df -h / | awk 'NR==2{print $4}')"

if [[ -z "$obsbot_nodes" || -z "$capture_node" ]]; then
  echo "ERROR: OBSBOT video capture node was not identified" >&2
  exit 1
fi
if [[ -z "$capture_card" || -z "$playback_card" ]]; then
  echo "ERROR: AT-CSP1 ALSA capture/playback card was not identified" >&2
  exit 1
fi
if [[ "$cuda_summary" == "not detected" ]]; then
  echo "ERROR: CUDA was not detected" >&2
  exit 1
fi

mkdir -p docs
{
  echo '# Jetson reconnaissance'
  echo
  echo "Generated on: $(date '+%Y-%m-%d %H:%M:%S %Z')"
  echo
  echo '## Acceptance summary'
  echo
  echo "- CUDA: $cuda_summary"
  echo "- Python: $python_summary"
  echo "- OBSBOT video nodes: $obsbot_nodes"
  echo "- Selected OBSBOT capture node: $capture_node"
  echo "- Pan/tilt controls: $ptz_controls"
  echo "- AT-CSP1 ALSA capture card: $capture_card"
  echo "- AT-CSP1 ALSA playback card: $playback_card"
  echo "- Available RAM: $available_ram"
  echo "- Available disk on /: $available_disk"
  echo
  echo '## Raw inventory'
  echo
  echo '```text'
  sed 's/```/` ` `/g' "$inventory_file"
  echo '```'
} > docs/recon.md

echo "OBSBOT video nodes: $obsbot_nodes (capture: $capture_node)"
echo "AT-CSP1 ALSA capture card: $capture_card; playback card: $playback_card"
echo "CUDA: $cuda_summary; Python: $python_summary"
echo "Available RAM: $available_ram"
echo "Available disk on /: $available_disk"
