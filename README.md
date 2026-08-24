# Gemma Companion

**An on-device AI companion that can see, hear, speak, and look for itself.**

> When Gemma doesn't know, it doesn't ask you for another picture. It looks.

- Real-Life Akinator finds what you are thinking of by inspecting the room and asking short yes/no questions.
- The elderly-friendly finder locates what you have misplaced and describes where it is in plain speech.
- The entire perception-and-action loop runs locally on one 8 GB Jetson; the Mac is development-only.

Gemma Companion is built for **Best Use of Gemma** (primary) and **Best Elderly Hack** (secondary).

## Why Gemma is essential

Gemma is not a replaceable chat layer. A local **Gemma 4 E2B instruction-tuned QAT Q4_0** model sees individual OBSBOT frames, reasons over directional memory, and emits structured `look_*` tool calls. Those calls move the physical camera through bounded UVC controls; only then is a fresh JPEG captured and returned to Gemma. This closes the perception-action loop that defines the product.

The verified runtime is the OpenAI-compatible `llama-server` bundled with Ollama 0.32.15, using its JetPack 6 CUDA backend. The model is Ollama's [`gemma4:e2b-it-qat`](https://ollama.com/library/gemma4%3Ae2b-it-qat), corresponding to Google's multimodal [Gemma 4 E2B instruction-tuned model](https://huggingface.co/google/gemma-4-E2B-it). The Q4_0 text model is 3.10 GiB; its multimodal projector is 942 MiB. Model weights and runtime binaries are deliberately excluded from git and remain subject to their own licenses/terms.

Measured on the Jetson Orin Nano Super:

| Operation | Runtime / license | Accepted latency |
|---|---|---:|
| Text → text | Gemma 4 E2B Q4_0 / Gemma terms | 0.301 s |
| 1024 px live image → text | Gemma 4 E2B Q4_0 / Gemma terms | 1.861 s |
| Parseable tool call | Gemma 4 E2B Q4_0 / Gemma terms | 0.436 s |
| Neutral Whisper transcription | whisper.cpp tiny.en Q5_1 / MIT runtime | 1.454–1.470 s |
| Agentic transcript → physical PTZ | Gemma tool gate + UVC | ≤2.139 s |
| Agentic fresh visual answer | Gemma tool gate + capture + vision | 4.871 s |
| Natural TTS, warm first audio | Kokoro-82M via kokoro-onnx 0.6.1, `af_heart` / Apache-2.0 model, MIT runtime | 1.311 s |
| Natural TTS, cached clip start | Kokoro-82M via kokoro-onnx 0.6.1, `af_heart` / Apache-2.0 model, MIT runtime | 0.005 s |
| Full Akinator games | End-to-end application / MIT | 21.506–40.590 s |
| Full requested-object finder runs | End-to-end application / MIT | 24.835–25.627 s |

The final physical companion regression retained 2.5 GiB available. A separate TTS verifier, which temporarily loaded a second Kokoro instance alongside the boot service, retained 2.114 GiB and measured 414.9 MiB TTS RSS. The loop aborts below 500 MiB.

## Architecture

```text
AT-CSP1 microphone
        │ continuous 16 kHz PCM; temporary utterance WAV
        ▼
whisper.cpp tiny.en ──► Gemma semantic function gate ──► ordinary answer
                                  │
                ┌─────────────────┼────────────────────┐
                │ LOOK tools      │ inspect_view       │ find_object / volume / stop
                ▼                 ▼                    ▼
        bounded UVC pan/tilt  fresh OBSBOT JPEG   deterministic local action
                │                 │
                └─────────────────┴──────► Gemma 4 E2B Q4_0
                                                  │
                                                  ▼
                                      Kokoro-82M → AT-CSP1 speaker

Every action and latency ──► logs/session-*.jsonl
```

Video is never streamed into the model. A session starts with bounded observations, keeps a compact directional inventory, allows at most 8 tool calls and 12 questions, and captures another still only when needed.

## Supported hardware

The released configuration is intentionally hardware-specific:

- NVIDIA Jetson Orin Nano Super 8 GB, aarch64, JetPack 6 / Ubuntu 24.04
- OBSBOT Tiny SE camera/gimbal with UVC absolute pan and tilt
- Audio-Technica AT-CSP1 USB microphone/speaker
- An NVMe system disk with room for several gigabytes of local runtime and model assets

The accepted machine used L4T R39.2.1, Python 3.12, a 500 GB Transcend NVMe, OBSBOT capture on `/dev/video0`, and the AT-CSP1 ALSA alias `Device`. Other Linux computers, JetPack releases, cameras, and audio devices are not yet verified. See [`docs/recon.md`](docs/recon.md) for the exact accepted inventory and [`docs/memory-budget.md`](docs/memory-budget.md) for measured memory.

## Install on a fresh Jetson

Setup needs internet access once. Normal use is fully offline.

### 1. Install operating-system prerequisites

Start from a working JetPack 6 image with CUDA userspace already present, then install the small host-side dependencies:

```bash
sudo apt-get update
sudo apt-get install -y \
  alsa-utils ca-certificates curl espeak-ng git \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-tools \
  python3 python3-pip python3-venv usbutils zstd
```

Do not run `apt upgrade` as part of this project setup. JetPack, CUDA, and kernel upgrades should be handled as a separate system-administration task.

### 2. Clone and connect the hardware

Use a clone path without spaces. Connect both USB devices before running reconnaissance:

```bash
git clone https://github.com/ilhamfp/GemmaCompanion.git ~/gemma-companion
cd ~/gemma-companion
./scripts/recon.sh
```

`recon.sh` exits nonzero unless it can identify CUDA, an OBSBOT capture node, UVC pan/tilt controls, and AT-CSP1 capture/playback. It writes the full inventory to `docs/recon.md`. If your OBSBOT capture node is not `/dev/video0`, note the selected node for the configuration step below.

### 3. Download the pinned local runtime and models

```bash
./scripts/bootstrap_runtime.sh
./scripts/bootstrap_tts.sh
make runtime
```

The first script downloads checksum-pinned Ollama 0.32.15 ARM64 and JetPack 6 runtime archives, pulls `gemma4:e2b-it-qat`, and installs the pinned whisper.cpp b4938 runtime plus `tiny.en`. The second creates `.venv`, installs the pinned CPU-only Kokoro ONNX stack, and downloads the Kokoro model and voice data. All generated assets live under `.runtime/`, `.venv/`, `models/`, `captures/`, `artifacts/`, or `logs/`; all are gitignored and model weights are never committed.

If DNS is unavailable on the Jetson, run the bootstrap on another compatible aarch64 JetPack 6 system and copy those generated directories into the same paths. Runtime and model assets retain their upstream licenses.

### 4. Verify each hardware layer

Run these before installing the boot service. The PTZ and companion checks physically move the OBSBOT, while audio and TTS checks use the speaker:

```bash
./scripts/test_camera.py
./scripts/test_ptz.py
./scripts/test_audio.py --text
./scripts/test_gemma.py
./scripts/test_tts.py
./scripts/test_companion.py
```

For the real microphone check, run `./scripts/test_audio.py` without `--text` and repeat the prompted sentence. Every verifier exits nonzero on failure and prints its accepted frame, device, latency, and/or memory evidence.

### 5. Run once in the foreground

Keep the AT-CSP1 microphone physically muted, then run:

```bash
make companion
```

Wait for `Hi, I'm Gemma!`. Unmute, speak one request, then mute again to close the utterance. Press `Ctrl-C` to stop the foreground session. Only one companion may own the camera and audio stream at once.

### 6. Enable automatic startup

After the foreground run succeeds, install the system service once:

```bash
sudo ./scripts/install_boot_service.sh
./scripts/test_boot_service.sh
```

The installer detects the account that invoked `sudo` and the current clone path, renders those into the unit, enables it, and starts it immediately. If the repository is owned by a different account, use `sudo env GEMMA_SERVICE_USER=<account> ./scripts/install_boot_service.sh`. The service waits up to two minutes for both USB devices, starts Gemma and Whisper locally, centers the camera, inspects one fresh frame, and then says `Hi, I'm Gemma!`.

To inspect the rendered unit without changing the system, run `./scripts/install_boot_service.sh --dry-run`.

After this one-time installation, attach the OBSBOT and AT-CSP1 before applying power. No Mac, login, Wi-Fi, display, or terminal is required after the greeting. See [`docs/LIVE_COMPANION.md`](docs/LIVE_COMPANION.md) for the physical button workflow and [`docs/DEMO_FLOW.md`](docs/DEMO_FLOW.md) for the rehearsed presentation.

## Run the demos

For the continuous, tactile companion session, keep the AT-CSP1 microphone muted and run:

```bash
make companion
```

Once Gemma says `Hi, I'm Gemma!`, unmute, speak, and mute again. That exact greeting is emitted only after the camera has centered, a fresh frame has been inspected, and continuous capture is live. Voice onset interrupts any current reply. There is no user-phrase router: each transcript reaches Gemma's semantic function gate, which may move or inspect the camera, search for an object, change speaker volume, stop, sleep, or answer normally. Paraphrases such as `aim toward port`, `decipher the card I'm presenting`, and `raise your speaking loudness` are verified. See [`docs/LIVE_COMPANION.md`](docs/LIVE_COMPANION.md) for the one-time boot-service installation and [`docs/DEMO_FLOW.md`](docs/DEMO_FLOW.md) for the exact five-beat no-Mac presentation.

The microphone PCM stream remains open so physical unmute can be detected immediately, but raw audio is not retained. Only a detected utterance becomes a temporary WAV for local Whisper, and that file is deleted after transcription.

Gemma 4's native audio path was also tested directly: a real `Find my glasses` WAV selected `find_object` without Whisper in 2.524 seconds with 2.888 GiB free. It is not the stage default because this 8 GB runtime cannot reliably keep native-audio and GPU-vision projector state in one long-lived process; mixed turns can exhaust CUDA memory. [`scripts/experiment_direct_audio.py`](scripts/experiment_direct_audio.py) therefore requires an isolated one-slot server, while the reliable boot service uses neutral-prompt Whisper and a two-slot vision server.

The AT-CSP1 starts at 100% playback volume. While the companion is running, requests such as `volume up`, `make your voice softer`, or `set volume to 90 percent` let Gemma select the appropriate mixer tool; execution changes the USB hardware mixer immediately. From a terminal, use `make volume VOLUME=90`. Set `GEMMA_PLAYBACK_VOLUME` to change the boot default.

The bounded Akinator and object-finder demos remain available below.

Reset first. It recenters the camera; every demo process creates fresh in-memory state while retaining evidence logs:

```bash
make reset
```

Real-Life Akinator, voice input and spoken output:

```bash
make demo-akinator
```

Keyboard-input fallback (spoken output remains enabled):

```bash
make demo-akinator DEMO_ARGS=--text
```

The verified elderly-friendly demo finds the small white Audio-Technica tabletop speaker after it moves out of the initial view:

```bash
make demo-elderly
```

The finder is generic. For staged glasses, run:

```bash
make demo-elderly DEMO_ARGS="--request 'Please find my glasses' --target 'wearable eyeglasses'"
```

`make demo-elderly` supplies the verified deterministic request but still speaks through the AT-CSP1. For a live voice request, omit `--request` and `--text`:

```bash
.venv/bin/python main.py --mode elderly --target 'wearable eyeglasses'
```

For keyboard request entry, add `--text`. Both paths use the same finder, spoken confirmation, physical camera tools, and result.

## Configuration

The tested defaults require no configuration. For a different detected device node or preferred voice, export variables before `make companion`:

| Variable | Default | Purpose |
|---|---|---|
| `GEMMA_CAMERA_DEVICE` | `/dev/video0` | OBSBOT V4L2 capture/control node |
| `GEMMA_AUDIO_CAPTURE_DEVICE` | `plughw:CARD=Device,DEV=0` | ALSA microphone device |
| `GEMMA_AUDIO_PLAYBACK_DEVICE` | `plughw:CARD=Device,DEV=0` | ALSA speaker device |
| `GEMMA_AUDIO_CARD` | `Device` | ALSA mixer card used by volume control |
| `GEMMA_PLAYBACK_VOLUME` | `100` | Startup hardware volume, 0–100 |
| `GEMMA_TTS_VOICE` | `af_heart` | Kokoro voice name |
| `GEMMA_TTS_SPEED` | `1.08` | Base speech speed, 0.5–2.0 |
| `GEMMA_TTS_THREADS` | `6` | CPU threads reserved for Kokoro |
| `GEMMA_VOICE_START_RMS` | `700` | Calibrated voice-onset threshold |
| `GEMMA_VOICE_END_RMS` | `350` | Calibrated mute/silence threshold |

For the system service, put overrides in `/etc/default/gemma-companion` using systemd environment-file syntax, then restart:

```ini
GEMMA_CAMERA_DEVICE=/dev/video2
GEMMA_PLAYBACK_VOLUME=90
```

```bash
sudo systemctl restart gemma-companion.service
```

From the development Mac, restart the installed Jetson service without a password prompt:

```bash
make restart
```

The boot-service installer grants the service account passwordless access only to the exact
`systemctl restart gemma-companion.service` operation. SSH must already use key authentication.
Override the default Jetson address when needed with
`GEMMA_REMOTE_HOST=user@host make restart`.

`make restart` waits for a new process, a new companion log, both local model endpoints, and
Gemma's grounded startup greeting. A successful command therefore means the newly restarted
session is ready, rather than merely that systemd started a process.

Do not set `GEMMA_SPEECH_MODE=direct` for the boot service on an 8 GB Jetson. Native Gemma audio is an isolated experiment described below, not the reliable vision configuration.

## Updating an installed companion

```bash
cd ~/gemma-companion
git pull --ff-only origin main
./scripts/bootstrap_runtime.sh
./scripts/bootstrap_tts.sh
sudo ./scripts/install_boot_service.sh
./scripts/test_boot_service.sh
```

The bootstraps are idempotent and checksum existing downloads. Re-running the installer refreshes the unit if the clone path or service definition changed.

## Troubleshooting

| Symptom | Check |
|---|---|
| `another Gemma Companion session is already running` | The boot service already owns the hardware. Use it, or run `sudo systemctl stop gemma-companion.service` before a foreground session. |
| No greeting after four minutes | Run `systemctl --no-pager --full status gemma-companion.service`, then `journalctl -u gemma-companion.service -n 100 --no-pager`. |
| Camera capture fails | Run `./scripts/recon.sh`, inspect `/dev/video*`, and set `GEMMA_CAMERA_DEVICE` to the selected capture node. |
| Microphone or playback fails | Compare `arecord -l` and `aplay -l` with the ALSA variables above; keep the AT-CSP1 connected before boot. |
| Gemma or Whisper does not start | Inspect `logs/gemma-server.log` and `logs/whisper-server.log`; rerun the corresponding bootstrap if an asset is missing. |
| Responses stop under load | Check `free -h`. The loop deliberately refuses inference below 500 MiB available; stop unrelated memory-heavy processes. |
| Finder is uncertain | Keep the target fully visible with useful contrast. The bounded sweep prefers an honest not-found result over inventing a location. |

To reset the camera without deleting logs or captures, run `make reset`. For a clean shutdown, use Ubuntu's power menu or `sudo poweroff` and wait for shutdown before disconnecting power.

## Privacy, safety, and reliability

- Runtime inference, STT, TTS, camera control, and logs stay on the Jetson. Network access is not used after setup.
- Only requested still images are processed; there is no video stream and no cloud API.
- PTZ commands are absolute and bounded to ±120° pan (inside the queried ±130° hardware stop) and ±30° tilt.
- The elderly mode locates objects only. It does not provide medical advice, medication dosage/timing, diagnosis, or emergency claims; it directs those questions to a caregiver or doctor.
- A not-found result is valid. The agent never invents a location when visual evidence is missing.
- Full contextual frames may ground a find directly. A magnified edge crop may only override a full-frame miss after a separate target-blind inventory and strict identity check agree, preventing cables or similarly colored fragments from becoming false finds.
- Every inference checks the 500 MiB available-memory guard, and every session is bounded.

## Honest fallbacks and verification choices

- **TTS:** Kokoro-82M via `kokoro-onnx` is the accepted natural, fully offline, CPU-only engine. The resident `af_heart` voice was selected by the human operator; eSpeak NG is retained only as a warning-logged runtime fallback.
- **STT:** whisper.cpp `tiny.en`, 75 MiB, fully offline. Keyboard `--text` mode is available for noisy rooms.
- **M7 target change:** physical glasses could not be staged inside the useful camera sweep. At the human's explicit request, the final verified target became the connected white Audio-Technica tabletop speaker. The same generic finder still accepts `wearable eyeglasses` when they are staged clearly.
- **M7 negative test:** a saved live five-direction baseline was re-evaluated for a genuinely absent red umbrella. It produced the honest not-found response.
- **Akinator acceptance:** repeatability verification used a scripted truthful text respondent; Gemma's visual reasoning, questions, tool calls, physical moves, guesses, TTS, and logs were all live.

All milestone evidence is verbatim in [`docs/STATUS.md`](docs/STATUS.md), with the full command log in [`docs/progress.md`](docs/progress.md).

## What is live versus staged in the video

Live: local Gemma inference, fresh OBSBOT captures, Gemma-issued camera tools, UVC motion, room observations, spoken lines, user answers, object locations, and JSONL logging.

Staged: a known set of easy-to-recognize room objects for Akinator and a known placement of the Audio-Technica speaker. The product behavior and model outputs are not replaced by a prerecorded response. See [`docs/demo-checklist.md`](docs/demo-checklist.md) for the ≤3-minute recording plan.

## Project structure

```text
agent/      shared Gemma client, bounded loop, prompts, memory
audio/      ALSA capture/playback, whisper.cpp STT, resident Kokoro TTS
camera/     fresh MJPEG capture and physical UVC pan/tilt
demos/      Akinator and elderly-friendly requested-object goals
tools/      deterministic schemas and physical dispatch
scripts/    recon, runtime bootstrap/start, continuous companion, and verifiers
docs/       PRD, operating contract, evidence ledger, command log
```

## License

Application code is released under the [MIT License](LICENSE). The Kokoro-82M model is Apache-2.0 and the `kokoro-onnx` runtime is MIT-licensed. Gemma, Ollama/llama.cpp runtime assets, whisper.cpp, its model, and eSpeak NG retain their respective upstream licenses.
