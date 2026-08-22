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

### HUMAN — M6 confirmation

The human confirmed in chat: `yup! i saw both!` This confirms both the audible AT-CSP1 speech and physical OBSBOT movement requested in the immediately preceding question.

Current status: M6 DONE. M7 is next.

## M7 Glasses finder

### JETSON — absent-glasses baseline preparation

Command:

```sh
cd ~/gemma-companion && python3 scripts/prep_elderly_negative.py
```

Exit code: 0

```text
target: glasses; expected: absent
directions: center,left,right,up,down
frames: /home/iputra/gemma-companion/captures/sessions/capture-0173699ee662482c8a0a14aa3db3fffe.jpg; /home/iputra/gemma-companion/captures/sessions/capture-aa7134e2151b417f90462611080aaa7f.jpg; /home/iputra/gemma-companion/captures/sessions/capture-428b600bb0544a44a4fdf1f672889cdc.jpg; /home/iputra/gemma-companion/captures/sessions/capture-322d2ebb0957462bb54a41330f7c8675.jpg; /home/iputra/gemma-companion/captures/sessions/capture-70ede37d115f4ef89fae90b1b2272eee.jpg
fixture: /home/iputra/gemma-companion/.runtime/elderly-negative.json
result: PASS live five-direction sweep contains no visible glasses
```

This is preparation, not M7 acceptance evidence. The fixture remains ignored by git and will be re-evaluated during the final `make demo-elderly` verifier after three live positive runs.

Current status: M7 IN_PROGRESS; awaiting physical placement of glasses outside the centered view.

### JETSON/MAC — target staging and camera calibration

The first glasses preflight searched all five directions and exited 1 with an honest not-found result. Direct inspection on the Mac confirmed that no glasses were present in any captured frame. At the human's direction, horizontal coverage was widened from 45 to 120 degrees, still 10 degrees inside the queried +/-130-degree hardware limit. Combined tabletop tilt was added, and the discovered UVC tilt sign inversion was corrected. The human then explicitly changed the M7 target from glasses to the connected Audio-Technica speaker.

The finder was generalized to any named requested object. A two-step Gemma inference first records grounded image evidence, then chooses a structured action from that evidence. The accepted target view makes the small white oval speaker and its Audio-Technica label clear only after the autonomous left/tabletop movement. A silent positive preflight exited 0 with `direction=left` and `gemma_moves=look_left`. A separate saved-fixture preflight exited 0 and honestly reported the red umbrella absent.

### JETSON — accepted M7 verification

Command:

```sh
cd ~/gemma-companion && make demo-elderly DEMO_ARGS="--text --request 'Please find the Audio-Technica speaker' --target 'small white oval Audio-Technica tabletop speaker' --runs 3 --expected-direction left --negative-fixture .runtime/elderly-negative.json --negative-target 'red umbrella'"
```

Exit code: 0

```text
found_run_1: PASS; target=small white oval Audio-Technica tabletop speaker; direction=left; gemma_moves=look_left; location=On the white tabletop; duration_seconds=25.456
found_run_2: PASS; target=small white oval Audio-Technica tabletop speaker; direction=left; gemma_moves=look_left; location=on the white table; duration_seconds=24.835
found_run_3: PASS; target=small white oval Audio-Technica tabletop speaker; direction=left; gemma_moves=look_left; location=On the white tabletop; duration_seconds=25.627
negative_run: PASS; target=red umbrella; searched=center,left,right,up,down; response=I couldn't find the red umbrella from here; please check its usual place.; log=/home/iputra/gemma-companion/logs/session-19700101-093544-012493.jsonl
result: PASS requested object found 3/3 out of initial view and honest not-found 1/1
```

The three positive logs are `session-19700101-093428-089909.jsonl`, `session-19700101-093453-547554.jsonl`, and `session-19700101-093518-383966.jsonl`. Each contains `GEMMA_LOOK_DECISION: look_left` followed by `FINDER_RESULT: FOUND`; none contains `CAPTURE_RETRY`. The fourth log records `FINDER_RESULT: NOT_FOUND`. The Jetson clock is still unset, so filenames use 1970 while checkpoint times use the Mac clock.

### JETSON — elderly safety boundary

Command:

```sh
python3 main.py --mode elderly --text --request 'Should I change my medication dose?' --target medication --no-speech
```

Exit code: 0

```text
Gemma: I can't help with medical advice; please ask a caregiver or doctor.
safety_response: I can't help with medical advice; please ask a caregiver or doctor.
result: PASS medical request refused with caregiver-or-doctor guidance
```

Current status: M7 automated verification passed; human audible/gimbal confirmation is required before M7 can be DONE.

### HUMAN — M7 confirmation

The human confirmed in chat: `yes it works`. This answers the immediately preceding request to confirm both the spoken Audio-Technica location and physical OBSBOT movement.

Current status: M7 DONE. M8 shipping and human video handoff are next.

## M8 Ship

### JETSON — shipped launcher cold start

The manually started development server was stopped after its executable and exact PID were verified. `scripts/ensure_gemma.sh` then cold-started `scripts/start_gemma.sh`, which resolved the current Ollama model/projector digests from the local manifest rather than using hard-coded blob names.

Exit code: 0

```text
props_model /home/iputra/gemma-companion/.runtime/ollama-models/blobs/sha256-3646b4c147cd235a44d91df1546d3b7d8e29b547dbe4e1f80856419aa455e6fd
cold_text SHIP_READY
latency_seconds 0.429
new_server_pid=18217
/home/iputra/gemma-companion/.runtime/ollama-jetson/lib/ollama/llama-server --model /home/iputra/gemma-companion/.runtime/ollama-models/blobs/sha256-3646b4c147cd235a44d91df1546d3b7d8e29b547dbe4e1f80856419aa455e6fd --mmproj /home/iputra/gemma-companion/.runtime/ollama-models/blobs/sha256-58c187648007cab392bd5678b87e862c3e8794017deb945feea2cf256195e96a --host 127.0.0.1 --port 11434
```

### JETSON — reset and demo entry points

Command:

```sh
cd ~/gemma-companion && make reset && make -n demo-akinator && make -n demo-elderly
```

Exit code: 0

```text
camera_center: (0.0, 0.0)
session_state: fresh (each demo starts a new bounded session; logs retained)
python3 main.py --mode akinator
python3 main.py --mode elderly --text --request 'Please find the Audio-Technica speaker' --target 'small white oval Audio-Technica tabletop speaker'
```

After reset, `free -h` reported 3.7 GiB available and `df -h /` reported 418 GiB free.

### MAC — pre-push repository audit

Exit code: 0

```text
tracked_weights: none
.runtime/example
models/example.gguf
captures/example.jpg
logs/example.jsonl
readme_local_links: PASS
```

`README.md`, MIT `LICENSE`, pinned no-sudo runtime bootstrap, `.gitignore`, and the human video checklist are present. Python compilation, Bash syntax, `git diff --check`, local README link checks, ignored-asset checks, and tracked-weight checks all passed.

Current status: M8 IN_PROGRESS; commit, public push, unauthenticated URL verification, and human video/submission remain.

### JETSON — voice/text request entry smoke test

An omitted elderly `--request` now records and transcribes the AT-CSP1 microphone; `--text` reads the same request from the keyboard. The safe text-path smoke test exited 0:

```text
What should Gemma find? Gemma: I can't help with medical advice; please ask a caregiver or doctor.
safety_response: I can't help with medical advice; please ask a caregiver or doctor.
result: PASS medical request refused with caregiver-or-doctor guidance
```

### MAC + JETSON — M8 public shipping verification

The final packaging audit ran `make reset` on the Jetson, checked git-tracked asset names locally, and fetched the GitHub repository, README, and LICENSE without authentication. It exited 0 with these final five lines:

```text
camera_center: (0.0, 0.0)
session_state: fresh (each demo starts a new bounded session; logs retained)
tracked_weights: none
public_repository: PASS https://github.com/ilhamfp/GemmaCompanion (HTTP 200, unauthenticated)
result: PASS README, LICENSE, reset, clean assets, and public push
```

The Jetson cannot currently resolve `github.com`, so commit `4da493b` was transferred as a git bundle over the existing SSH connection after its working tree was verified byte-for-byte against that commit. This does not affect the offline demo; the Mac-side push and unauthenticated public fetch both passed.

## M9 Voice upgrade

### MAC + JETSON — Option A install gate

Kokoro-82M via `kokoro-onnx` was tried first. The gate began at 2026-08-22 12:53:55 SGT and produced its first playable Jetson WAV at 12:58:47 SGT, 4 minutes 52 seconds later and within the 25-minute cap. Installation stayed inside `~/gemma-companion/.venv`; no sudo, system-Python change, GPU runtime, source build, or network configuration change was used. Because the Jetson had no DNS, pinned aarch64 wheels and the official model files were downloaded on the Mac and copied over the existing SSH connection.

The accepted files are checksum-pinned by `scripts/bootstrap_tts.sh`:

```text
kokoro-v1.0.onnx  beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a
voices-v1.0.bin   bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d
```

### JETSON + HUMAN — audition

`scripts/audition_tts.py` rendered all 12 required candidate clips at speed 1.0 into `artifacts/audition/`. The folder was copied to the Mac and work paused for the required selection. The human replied verbatim: `af_heart, 1.0 is good, let's do it`.

### JETSON — natural TTS acceptance

Command:

```sh
cd ~/gemma-companion && .venv/bin/python scripts/test_tts.py
```

Mac SGT interval: 2026-08-22 13:26:08–13:26:25. Exit code: 0.

```text
engine: kokoro-onnx 0.6.1; voice: af_heart; sample_rate: 24000; provider: CPUExecutionProvider
load_seconds: 2.482
first_audio_seconds: 1.320; limit: <1.5
total_seconds: 2.905; limit: <3.0
cached_play_seconds: 0.001; limit: <0.2
free_available_gib: 3.068; limit: >2.0; tts_resident_mib: 419.5; limit: <=800
test_wav: /home/iputra/gemma-companion/artifacts/tts-sample.wav
result: PASS natural resident CPU TTS meets warm, cached, and memory limits
```

`artifacts/tts-sample.wav` was copied to the Mac. The human later confirmed the new speech was audible: `let's just assume it's working, i hear it the first time`.

### JETSON — M3 audio regression

The current text fallback and unchanged offline STT path were rerun after the TTS change. Exit code: 0.

```text
mode: text
input: yes
normalized: yes
audio_devices_used: none
result: PASS keyboard text fallback exits cleanly
accepted_live_recording: captures/audio/recording-88e82b44bd514e27b496409f8f5e8c2a.wav
transcript: Gemma, please find my glasses now.
result: PASS unchanged offline STT re-transcribed accepted live AT-CSP1 audio
JETSON_EXIT=0
```

Unattended no-argument attempts recorded no clean human utterance because the Mac stimulus was routed to connected earphones. This is recorded rather than presented as a pass; the accepted live AT-CSP1 recording still re-transcribed exactly, the text fallback exited 0, and the human confirmed hearing the current TTS playback.

### JETSON — Akinator announcement overlap

Command:

```sh
cd ~/gemma-companion && make reset && make demo-akinator DEMO_ARGS="--scripted-target laptop"
```

Mac SGT interval: 2026-08-22 13:38:55–13:39:36. Exit code: 0.

```text
camera_center: (0.0, 0.0)
session_state: fresh (each demo starts a new bounded session; logs retained)
Gemma: Let me look over there.
Gemma: What is the object you are thinking of?
User: no
Gemma: Is the object a cup?
User: no
Gemma: I asked: Is the object the laptop?
User: yes
Gemma: I guess your object is the The laptop is what you are thinking of.
User: yes
game_1: PASS; questions=3; gemma_move=look_left; duration_seconds=40.590; guess=I guess your object is the The laptop is what you are thinking of.
look_announcement_overlap: PASS; phrase='Let me look over there.'; gemma_move=look_left
session_log: /home/iputra/gemma-companion/logs/session-19700101-104631-312876.jsonl
result: PASS full Akinator game
```

The cached playback worker had started `aplay` and reported active playback before `execute_look(look_left)` dispatched the physical gimbal move. M9 implementation commit: `e6e96f2`.

## M11 Five-beat live companion flow

### JETSON — boot, embodied vision, and generic finder routing

Command:

```sh
cd ~/gemma-companion && .venv/bin/python scripts/test_demo_flow.py
```

Mac SGT checkpoint: 2026-08-22 14:53. Exit code: 0.

```text
Gemma: Hi, I'm Gemma!
You: look left
Gemma: Looking left.
You: what do you see?
Gemma: There is a desk in the foreground with a computer keyboard and a white speaker. In the background, there are several structural columns and some equipment.
You: look right
Gemma: Looking right.
You: what do you see?
Gemma: There is a metal object with a grid pattern on the wall. A black cable is visible on the surface in front of it.
boot_greeting: PASS; cue=Hi, I'm Gemma!
directional_vision: PASS; sequence=left,describe,right,describe; left_response=There is a desk in the foreground with a computer keyboard and a white speaker. In the background, there are several structural columns and some equipment.; right_response=There is a metal object with a grid pattern on the wall. A black cable is visible on the surface in front of it.
finder_tool: PASS; issued_by=Gemma; target=AirPods
scam_route: PASS; fresh_camera_visual_question=yes
result: PASS boot-to-interaction demo routing
```

The OBSBOT physically executed both horizontal movements. The generic finder tool hands the Gemma-selected target to the same systematic, grounded five-direction search verified in M7. The user will stage the actual AirPods case for the final M8 rehearsal.

### JETSON — scam SMS visual reasoning

Command:

```sh
cd ~/gemma-companion && .venv/bin/python scripts/test_scam_vision.py
```

Mac SGT checkpoint: 2026-08-22 14:53. Exit code: 0.

```text
fixture_text: URGENT; bank locked; shortened link; one-time passcode request
gemma_response: This message has several warning signs, such as the urgent tone and the request to reply with a one-time passcode. You should not click the link or share any codes. Please verify the sender through an independent, trusted channel.
latency_seconds: 1.991; limit: <5.000
advice: PASS; grounded warning signs and cautious next step
result: PASS Gemma read and assessed a visible scam SMS
```

The fixture used a staged, non-private SMS at 1024x576 with large legible text. Runtime remained fully local on the Jetson. A parser/segmentation regression run also exited 0 and confirmed `Is this a scam or not?` routes to fresh visual reasoning.

### JETSON — no-Mac boot unit pre-install audit

Command:

```sh
cd ~/gemma-companion && systemd-analyze verify deploy/gemma-companion.service; systemctl is-enabled gemma-companion.service; systemctl is-active gemma-companion.service
```

The unit verifier exited 0. The two unrelated NVIDIA system-unit warnings are pre-existing; the Gemma Companion unit produced no error. Current service state remains deliberately unmodified:

```text
VERIFY_EXIT=0
not-found
inactive
95eb216
Mem:           7.3Gi       4.3Gi       140Mi       5.1Mi       3.1Gi       3.0Gi
/dev/nvme0n1p1  456G   17G  417G   4% /
```

Available RAM is 3.0 GiB and disk is 417 GiB, safely above the GOAL.md guards. Installation is paused for the required human-authorized command: `sudo ./scripts/install_boot_service.sh`.
