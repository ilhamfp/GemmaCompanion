# No-Mac live companion runbook

## One-time setup

The code and model assets must already be present in `/home/iputra/gemma-companion`. Install the system boot service once from a Jetson terminal or the current SSH session:

```bash
cd ~/gemma-companion
sudo ./scripts/install_boot_service.sh
```

Type the Jetson account password directly into that terminal. The installer copies only `deploy/gemma-companion.service`, reloads systemd, enables the unit for future boots, and starts it immediately.

Verify the installed service:

```bash
./scripts/test_boot_service.sh
```

## Power-on sequence

1. Connect the OBSBOT and AT-CSP1 before applying Jetson power.
2. Leave the AT-CSP1 microphone physically muted.
3. Apply power and wait. Ubuntu, the local Gemma server, the resident Whisper server, and the companion start automatically; no login, Mac, Wi-Fi, or keyboard is required.
4. OBSBOT centers and captures one fresh still.
5. Readiness is audible: Gemma says exactly `Hey, Gemma here!` after silently inspecting the centered fresh frame. This is the cue that vision, speech, and continuous capture are all live.
6. Unmute, speak one request, then mute. The muted return closes the utterance.

Cold-boot readiness can take roughly one to two minutes. Do not begin speaking until the audible readiness sentence.

## Physical interaction

Always use the same tactile rhythm:

```text
microphone muted -> unmute -> speak -> mute -> Gemma acts/answers
```

Examples:

- `Look left.` — direct bounded movement; no Gemma reasoning delay.
- `Look right.`
- `Look up.`
- `Look down.`
- `Look center.`
- `What do you see?` — captures a fresh still at the current physical direction, then answers.
- `Look left and tell me what you see.` — moves first, then captures and explains.
- `Stop.` or `Be quiet.` — cancels current playback.
- `Volume up.` or `Volume down.` — adjusts the AT-CSP1 by ten percentage points.
- `Set volume to 90 percent.` — selects an exact hardware playback level.
- `Go to sleep.` — remains locally available but ignores other requests.
- `Wake up.` — resumes normal requests.

To interrupt, do not wait for Gemma to finish. Unmute while it is speaking, say the new request, and mute again. Human voice onset terminates active playback; the newest request invalidates any older unfinished model response.

Playback defaults to 85% at each companion start. The voice commands above remain available throughout the session. From a Jetson terminal, `make volume VOLUME=90` provides the same adjustment; `GEMMA_PLAYBACK_VOLUME` changes the service default.

## Recommended live-demo sequence

1. Power on with the mic muted and both USB devices attached.
2. Film the OBSBOT centering and the `Hey, Gemma here!` readiness greeting.
3. Unmute, say `Look left`, and mute. Show the immediate physical movement.
4. Unmute, ask `What do you see?`, and mute. Capture the fresh grounded answer.
5. While Gemma is still speaking, unmute, say `Look right`, and mute. Its voice should stop and the OBSBOT should move right.
6. Ask `What do you see now?` and capture the changed answer.
7. Finish with `Look center`.

## Local privacy behavior

- Raw PCM is processed continuously in memory but is not saved.
- Only a detected utterance becomes a temporary WAV for local Whisper; it is deleted immediately afterward.
- Camera input is fresh still images, never a video stream.
- Gemma, Whisper, TTS, camera control, and logs all run on the Jetson.

## Recovery without a Mac

If no readiness sentence is heard after two minutes, use a temporarily attached display and keyboard, sign in, and run:

```bash
systemctl --no-pager --full status gemma-companion.service
journalctl -u gemma-companion.service -n 100 --no-pager
```

To restart it:

```bash
sudo systemctl restart gemma-companion.service
```

For a clean shutdown, use Ubuntu's power menu or `sudo poweroff` and wait for shutdown before disconnecting power.
