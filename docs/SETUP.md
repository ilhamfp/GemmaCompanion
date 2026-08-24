# Jetson setup and operations

This guide contains the detailed installation and maintenance material kept out of the project landing page. The verified target is an NVIDIA Jetson Orin Nano 8 GB running JetPack 6 / Ubuntu 24.04 with an OBSBOT Tiny SE and Audio-Technica AT-CSP1 connected over USB.

Other Linux computers, JetPack releases, cameras, ALSA aliases, and audio devices are not yet verified.

## 1. Install operating-system prerequisites

Start from a working JetPack 6 image with CUDA userspace already present. Do not run `apt upgrade` as part of project setup; treat JetPack, CUDA, and kernel upgrades as a separate system-administration task.

```bash
sudo apt-get update
sudo apt-get install -y \
  alsa-utils ca-certificates curl espeak-ng git \
  gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-tools \
  python3 python3-pip python3-venv usbutils zstd
```

## 2. Clone and identify the hardware

Use a clone path without spaces. Connect the OBSBOT and AT-CSP1 before reconnaissance.

```bash
git clone https://github.com/ilhamfp/GemmaCompanion.git ~/gemma-companion
cd ~/gemma-companion
./scripts/recon.sh
```

`recon.sh` exits nonzero unless it identifies CUDA, an OBSBOT capture node, UVC pan/tilt controls, and AT-CSP1 capture/playback. It writes the accepted inventory to [`recon.md`](recon.md).

The verified configuration uses OBSBOT capture on `/dev/video0` and the AT-CSP1 ALSA alias `Device`. The boot readiness probe is hardware-specific, so alternate ALSA card aliases are not currently supported without code changes.

## 3. Download the pinned local runtimes and models

```bash
./scripts/bootstrap_runtime.sh
./scripts/bootstrap_tts.sh
make runtime
```

The runtime bootstrap downloads checksum-pinned Ollama 0.32.15 ARM64 and JetPack 6 archives, pulls `gemma4:e2b-it-qat`, and installs whisper.cpp b4938 with `tiny.en`. The TTS bootstrap creates `.venv`, installs the pinned CPU-only Kokoro ONNX stack, and downloads the Kokoro model and voice data.

Generated assets live under `.runtime/`, `.venv/`, `models/`, `captures/`, `artifacts/`, or `logs/`. They are gitignored and retain their upstream licenses.

If DNS is unavailable on the Jetson, run the bootstrap on another compatible aarch64 JetPack 6 system and copy the generated directories into the same repository paths.

## 4. Verify each layer

The PTZ and companion checks physically move the OBSBOT. Audio and TTS checks play through the AT-CSP1.

```bash
./scripts/test_camera.py
./scripts/test_ptz.py
./scripts/test_audio.py --text
./scripts/test_gemma.py
./scripts/test_tts.py
./scripts/test_companion.py
make performance
```

For a real microphone check, run `./scripts/test_audio.py` without `--text` and repeat the prompted sentence. Each verifier exits nonzero on failure and prints its accepted device, frame, latency, and/or memory evidence.

## 5. Run in the foreground

Keep the AT-CSP1 microphone physically muted, then run:

```bash
make companion
```

Wait for `Hi, I'm Gemma!`. Unmute, speak one request, and mute again. Press `Ctrl-C` to stop. Only one companion process may own the camera and audio stream at a time.

## 6. Enable automatic startup

After the foreground run succeeds, install the service once:

```bash
sudo ./scripts/install_boot_service.sh
./scripts/test_boot_service.sh
```

The installer detects the account invoking `sudo` and the current clone path, renders those values into `gemma-companion.service`, enables the unit, and starts it immediately. It also installs a narrowly scoped sudoers rule that permits that account to restart only this service without a password.

If the repository belongs to another account, use:

```bash
sudo env GEMMA_SERVICE_USER=<account> ./scripts/install_boot_service.sh
```

Inspect the rendered service and sudoers rule without changing the system:

```bash
./scripts/install_boot_service.sh --dry-run
```

After installation, connect both USB devices before applying power. No Mac, login, network, display, or terminal is required after the readiness greeting. See [`LIVE_COMPANION.md`](LIVE_COMPANION.md) for the physical workflow.

## Configuration

The tested hardware needs no overrides. These environment variables tune the accepted devices and behavior:

| Variable | Default | Purpose |
|---|---|---|
| `GEMMA_CAMERA_DEVICE` | `/dev/video0` | OBSBOT V4L2 capture/control node |
| `GEMMA_AUDIO_CAPTURE_DEVICE` | `plughw:CARD=Device,DEV=0` | ALSA microphone device |
| `GEMMA_AUDIO_PLAYBACK_DEVICE` | `plughw:CARD=Device,DEV=0` | ALSA speaker device |
| `GEMMA_AUDIO_CARD` | `Device` | ALSA mixer card used by volume control |
| `GEMMA_PLAYBACK_VOLUME` | `100` | Startup hardware volume, 0–100 |
| `GEMMA_TTS_VOICE` | `af_heart` | Kokoro voice name |
| `GEMMA_TTS_SPEED` | `1.08` | Speech speed, 0.5–2.0 |
| `GEMMA_TTS_THREADS` | `6` | CPU threads reserved for Kokoro |
| `GEMMA_WHISPER_AUDIO_CONTEXT` | `1280` | Conservative speech context; verified against the 12-second segment bound |
| `GEMMA_VOICE_START_RMS` | `700` | Calibrated voice-onset threshold |
| `GEMMA_VOICE_END_RMS` | `350` | Calibrated mute/silence threshold |

The service reads overrides from `/etc/default/gemma-companion`. Restart after changing that file:

```bash
sudo systemctl restart gemma-companion.service
```

From the development Mac, restart the accepted Jetson target without an interactive password:

```bash
make restart
```

Override its SSH destination with `GEMMA_REMOTE_HOST=user@host make restart`. SSH key authentication must already work. The command succeeds only after a new process and session log exist, both local model endpoints respond, and the grounded startup greeting is recorded.

Do not set `GEMMA_SPEECH_MODE=direct` for the 8 GB boot service. Native Gemma audio is an isolated experiment documented in [`CONTINUOUS_COMPANION.md`](CONTINUOUS_COMPANION.md), not the reliable GPU-vision configuration.

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
| `another Gemma Companion session is already running` | The boot service owns the hardware. Use it, or stop it before a foreground run. |
| No greeting after two minutes | Run `systemctl --no-pager --full status gemma-companion.service`, then `journalctl -u gemma-companion.service -n 100 --no-pager`. |
| Camera capture fails | Run `./scripts/recon.sh`, inspect `/dev/video*`, and confirm the accepted OBSBOT node is `/dev/video0`. |
| Microphone or playback fails | Compare `arecord -l` and `aplay -l` with the accepted `Device` alias; attach the AT-CSP1 before boot. |
| Gemma or Whisper does not start | Inspect `logs/gemma-server.log` and `logs/whisper-server.log`, then rerun the relevant bootstrap. |
| Responses stop under load | Run `free -h`; inference deliberately refuses to start below 500 MiB available. |
| Finder is uncertain | Keep the target fully visible with useful contrast. An honest not-found result is preferred to an invented location. |

Reset the camera without deleting logs or captures with `make reset`. For a clean shutdown, use Ubuntu's power menu or `sudo poweroff` and wait for shutdown before disconnecting power.
