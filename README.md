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

## Hardware and tested platform

- NVIDIA Jetson Orin Nano Super 8 GB, aarch64, L4T R39.2.1 / Ubuntu 24.04
- Transcend 500 GB NVMe root disk
- OBSBOT Tiny SE camera/gimbal on `/dev/video0`
- Audio-Technica AT-CSP1 microphone/speaker on ALSA `plughw:3,0`
- Python 3.12, GStreamer, ALSA tools, Pillow

See [`docs/recon.md`](docs/recon.md) for the exact discovery output and [`docs/memory-budget.md`](docs/memory-budget.md) for measured memory.

## One-time setup on the Jetson

Clone into the tested path and bootstrap without installing weights into git:

```bash
git clone https://github.com/ilhamfp/GemmaCompanion.git ~/gemma-companion
cd ~/gemma-companion
./scripts/bootstrap_runtime.sh
./scripts/bootstrap_tts.sh
make runtime
```

The runtime bootstrap downloads pinned, checksum-verified official Ollama ARM64 and JetPack 6 archives, pulls `gemma4:e2b-it-qat`, downloads the official whisper.cpp b4938 ARM64 runtime and `tiny.en` model, and unpacks Ubuntu's eSpeak NG package without sudo. The TTS bootstrap creates the gitignored `.venv`, installs the pinned CPU-only Kokoro ONNX stack, and downloads checksum-verified `kokoro-v1.0.onnx` and `voices-v1.0.bin` into `models/`. It needs internet only once. The downloaded `.runtime/`, `.venv/`, and `models/` trees are ignored by git. If Jetson DNS is unavailable, run the downloads on another machine and copy the resulting runtime/model assets to the same repo paths.

The base image must already provide GStreamer, ALSA `arecord`/`aplay`, Python, the JetPack CUDA userspace, and eSpeak's shared-library dependencies. Kokoro stays resident on CPU and uses the selected `af_heart` voice at speed 1.08; eSpeak NG remains installed for phonemization and emergency runtime fallback. Run `./scripts/recon.sh` to verify the expected devices before a demo. Environment overrides are available for `GEMMA_CAMERA_DEVICE`, `GEMMA_AUDIO_CAPTURE_DEVICE`, and `GEMMA_AUDIO_PLAYBACK_DEVICE`.

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

## Privacy, safety, and reliability

- Runtime inference, STT, TTS, camera control, and logs stay on the Jetson. Network access is not used after setup.
- Only requested still images are processed; there is no video stream and no cloud API.
- PTZ commands are absolute and bounded to ±120° pan (inside the queried ±130° hardware stop) and ±30° tilt.
- The elderly mode locates objects only. It does not provide medical advice, medication dosage/timing, diagnosis, or emergency claims; it directs those questions to a caregiver or doctor.
- A not-found result is valid. The agent never invents a location when visual evidence is missing.
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
