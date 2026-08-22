# Build progress

Commands are labelled by execution host. Output below is real command output from this session.

## M0 Recon

### JETSON — identity check

Command:

```sh
ssh -o BatchMode=yes -o ConnectTimeout=10 iputra@192.168.55.1 'hostname && id'
```

Exit code: 0

```text
iputra
uid=1000(iputra) gid=1000(iputra) groups=1000(iputra),4(adm),24(cdrom),27(sudo),29(audio),30(dip),44(video),46(plugdev),100(users),114(i2c),125(gdm),984(weston-launch),985(gpio),993(render)
```

### JETSON — initial verification attempt

Command:

```sh
cd ~/gemma-companion && ./scripts/recon.sh
```

Exit code: 1

```text
ERROR: v4l2-ctl is required for camera recon
```

The verifier was changed to use sysfs and direct read-only V4L2 ioctls when `v4l2-ctl` is unavailable. No package or driver installation was needed.

### JETSON — final verification

Command:

```sh
cd ~/gemma-companion && ./scripts/recon.sh
```

Exit code: 0

```text
OBSBOT video nodes: /dev/video0,/dev/video1 (capture: /dev/video0)
AT-CSP1 ALSA capture card: 3; playback card: 3
CUDA: driver API 13.2 (nvidia-l4t-cuda installed); Python: Python 3.12.3
Available RAM: 6.4Gi
Available disk on /: 425G
```

Current status: M0 DONE. M1 is next.

## M1 Camera capture

### JETSON — cold-open verification attempt

Command:

```sh
cd ~/gemma-companion && ./scripts/test_camera.py
```

Exit code: 1

```text
AssertionError: capture took 2.028s; acceptance limit is 2.000s
```

### JETSON — accepted verification

Command:

```sh
cd ~/gemma-companion && ./scripts/test_camera.py
```

Exit code: 0

```text
device: /dev/video0
capture_path: /home/iputra/gemma-companion/captures/capture-a08718edb6eb4ddf9f6379098d99da87.jpg
dimensions: 1024x576; bytes: 62710; contrast_stddev: 83.61
elapsed_seconds: 0.392
result: PASS fresh JPEG captured in under 2 seconds
```

### MAC — copied-frame inspection

Command:

```sh
scp iputra@192.168.55.1:~/gemma-companion/captures/capture-a08718edb6eb4ddf9f6379098d99da87.jpg artifacts/m1-camera.jpg
```

Exit code: 0. SHA-256: `bc6a3c9ceaf292c113394a1c72e49a993bf3bc021a2fb545627343d7243ec8e0`.

Visual description: a laptop fills the left foreground; beyond it are a white desk, large monitor, black chair/bag, small plant, and boxes. This is the expected workspace view.

Current status: M0-M1 DONE. M2 is next.

## M2 PTZ control

### JETSON — verification

Command:

```sh
cd ~/gemma-companion && ./scripts/test_ptz.py
```

Exit code: 0

```text
method: uvc
sequence: look_left,capture,look_right,capture,look_center
frames: left=/home/iputra/gemma-companion/captures/ptz/capture-21bd82831ee442f6a6d9de25e4b6ef1f.jpg; right=/home/iputra/gemma-companion/captures/ptz/capture-1126905570eb412e956893d519583ea5.jpg
mean_pixel_diff: 76.458; threshold: 8.000
result: PASS physical PTZ frames differ and camera returned center
```

### MAC — frame inspection

Both frames were copied to `artifacts/`. The left frame is centered on the foreground laptop and far monitor; the right frame shifts across the workspace and adds two people and a window. The measured and visible view change confirms physical movement.

Current status: M0-M2 DONE. M3 is next.

## M3 Audio I/O

### JETSON — text fallback

Command:

```sh
cd ~/gemma-companion && ./scripts/test_audio.py --text --text-input "yes, please"
```

Exit code: 0

```text
mode: text
input: yes, please
normalized: yes, please
audio_devices_used: none
result: PASS keyboard text fallback exits cleanly
```

### JETSON — diagnostic human recording

An eight-second direct ALSA capture from `plughw:3,0` was transcribed locally to establish the correct mic path after the AT-CSP1 suppressed self-loopback through echo cancellation.

Exit code: 0

```text
Gemma, please find my glasses.
```

### JETSON — accepted verification

Command:

```sh
cd ~/gemma-companion && ./scripts/test_audio.py
```

Exit code: 0

```text
Speak now: Gemma, please find my glasses
recording: /home/iputra/gemma-companion/captures/audio/recording-88e82b44bd514e27b496409f8f5e8c2a.wav; duration_seconds: 3.000
transcript: Gemma, please find my glasses now.
spoken: Hello, I am Gemma; device: plughw:3,0
text_fallback: yes; status: PASS
result: PASS 3s record, offline STT, TTS playback, and text mode
```

The human reported hearing the AT-CSP1 playback in chat. A second `--text --text-input "yes, please"` invocation after the hardware run also exited 0.

Current status: M0-M2 DONE; M3 FALLBACK (counts as DONE). M4 is next.

## M4 Gemma on the Jetson

### JETSON — rejected generic CUDA runtime attempt

The generic ARM64 CUDA 13 backend detected the Orin GPU but showed 0% GR3D activity. A warm-server text response took 42.98 seconds at 0.04 generated tokens/s, so it was not accepted. The official JetPack 6 backend bundled with the same llama.cpp distribution was selected and showed GPU-backed inference.

### JETSON — accepted verification

Command:

```sh
cd ~/gemma-companion && ./scripts/test_gemma.py
```

Exit code: 0

```text
model: Gemma 4 E2B; tag: gemma4:e2b-it-qat; quantization: Q4_0; runtime: llama.cpp b1-9d77fa172 CUDA jetpack6
text_to_text: PASS; latency_seconds: 0.306; response: GEMMA_READY
image_to_text: PASS; latency_seconds: 2.099; response: The image displays a laptop, a person, and a chair.
tool_call: PASS; latency_seconds: 0.550; parsed: look_right
free_h_after_load: Mem:           7.3Gi       4.0Gi       135Mi       5.2Mi       3.4Gi       3.3Gi; result: PASS Gemma text, vision, tool call, latency, and RAM headroom
```

Current status: M0-M2 and M4 DONE; M3 FALLBACK (counts as DONE). M5 is next.

## M5 Agent loop

### JETSON — accepted verification

Command:

```sh
cd ~/gemma-companion && ./scripts/test_loop.py
```

Exit code: 0

```text
gemma_action: look_left; issued_by: Gemma; tool_calls: 1/8
physical_result: pan=-45.0; tilt=0.0; mean_pixel_diff=75.723
post_look_message: NEW_OBJECT: a microphone on the desk
session_log: /home/iputra/gemma-companion/logs/session-19700101-084916-060515.jsonl; events: 10; order: decide,look,capture,reference
result: PASS Gemma issued LOOK and its next visual message used only the new physical frame
```

The JSONL contains ten timestamped events. It records a Gemma-emitted `look_left` tool call, the UVC move to -45 degrees, a fresh capture, and then `NEW_OBJECT: a microphone on the desk`. Immediately after the run, `free -h` reported 4.1 GiB used and 3.2 GiB available; `df -h /` reported 418 GiB free.

Current status: M0-M2 and M4-M5 DONE; M3 FALLBACK (counts as DONE). M6 is next.

## M6 Akinator demo

### JETSON — dry runs and capture hardening

The first one-game text dry run failed because the scripted truthful-user helper answered `no` when Gemma directly named its laptop target. A deterministic exact-target answer fixed that verifier issue; the next one-game run passed in 18.735 seconds. The first two-game run then completed game one but received a transient truncated MJPEG during game two. The shared loop now retries a failed still capture at most three times and logs every retry. Neither failed attempt counts as acceptance evidence.

### JETSON — accepted two-game verification

Command:

```sh
cd ~/gemma-companion && make demo-akinator DEMO_ARGS='--text --scripted-target laptop --games 2'
```

Exit code: 0

```text
game_1: PASS; questions=1; gemma_move=look_left; duration_seconds=21.506; guess=I guess your object is the laptop.
game_2: PASS; questions=2; gemma_move=look_left; duration_seconds=28.872; guess=I guess your object is the laptop.
consecutive_games: 2/2 PASS; text_fallback: yes; physical_moves: 2
session_logs: /home/iputra/gemma-companion/logs/session-19700101-085459-445289.jsonl; /home/iputra/gemma-companion/logs/session-19700101-085520-951762.jsonl
result: PASS two consecutive full Akinator games with Gemma-initiated physical camera moves
```

Both accepted logs contain an independent `GEMMA_LOOK_DECISION` for `look_left`, a physical `LOOK`, and `GAME_RESULT: PASS`. There were no capture retries in either accepted game. The run used live AT-CSP1 speech output and scripted text answers. `free -h` afterward reported 4.3 GiB used and 3.0 GiB available; disk had 418 GiB free.

Current status: M6 automated verification passed; human audible/gimbal confirmation is required before M6 can be DONE. M7 has not started.

### JETSON — requested M6 replay

Command:

```sh
cd ~/gemma-companion && make demo-akinator DEMO_ARGS='--text --scripted-target laptop --games 2'
```

Exit code: 0

```text
game_1: PASS; questions=2; gemma_move=look_left; duration_seconds=27.903; guess=I guess your object is the laptop.
game_2: PASS; questions=1; gemma_move=look_left; duration_seconds=21.759; guess=I guess your object is the laptop.
consecutive_games: 2/2 PASS; text_fallback: yes; physical_moves: 2
session_logs: /home/iputra/gemma-companion/logs/session-19700101-090946-763935.jsonl; /home/iputra/gemma-companion/logs/session-19700101-091014-667650.jsonl
result: PASS two consecutive full Akinator games with Gemma-initiated physical camera moves
```

Both replay logs contain `GEMMA_LOOK_DECISION: look_left` and `GAME_RESULT: PASS`; neither contains `CAPTURE_RETRY`. Afterward, 2.9 GiB RAM and 418 GiB disk remained available. Human confirmation remains the final M6 gate.
