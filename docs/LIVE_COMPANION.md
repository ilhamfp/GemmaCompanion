# No-Mac live companion runbook

## One-time setup

The code and model assets must already be present in a clone path without spaces. Install the system boot service once from a Jetson terminal or the current SSH session:

```bash
cd ~/gemma-companion
sudo ./scripts/install_boot_service.sh
```

Type the Jetson account password directly into that terminal. The installer renders and installs only `deploy/gemma-companion.service`, reloads systemd, enables the unit for future boots, and starts it immediately.

The installer renders the invoking account and current repository path into the installed unit. If the repository belongs to another account, run `sudo env GEMMA_SERVICE_USER=<account> ./scripts/install_boot_service.sh`. Optional hardware overrides can be placed in `/etc/default/gemma-companion` before restarting the service. `./scripts/install_boot_service.sh --dry-run` previews the rendered unit without root access or system changes.

Verify the installed service:

```bash
./scripts/test_boot_service.sh
```

## Power-on sequence

1. Connect the OBSBOT and AT-CSP1 before applying Jetson power.
2. Leave the AT-CSP1 microphone physically muted.
3. Apply power and wait. Ubuntu, the local Gemma server, the resident Whisper server, and the companion start automatically; no login, Mac, Wi-Fi, or keyboard is required.
4. OBSBOT centers and captures one fresh still.
5. Readiness is audible: Gemma says exactly `Hi, I'm Gemma!` after silently inspecting the centered fresh frame. This is the cue that vision, speech, and continuous capture are all live.
6. Unmute, speak one request, then mute. The muted return closes the utterance.

Cold-boot readiness can take roughly one to two minutes. Do not begin speaking until the audible readiness sentence.

## Physical interaction

Always use the same tactile rhythm:

```text
microphone muted -> unmute -> speak -> mute -> Gemma acts/answers
```

Examples:

- `Look left.` — Gemma selects a bounded physical movement tool from the request's meaning.
- `Look right.`
- `Look up.`
- `Look down.`
- `Look center.`
- `What do you see?` — captures a fresh still at the current physical direction, then answers.
- `Look left and tell me what you see.` — moves first, then captures and explains.
- `Find my AirPods.` — Gemma extracts the generic visual target and searches center, left, right, up, and down until grounded evidence finds it or every view is exhausted.
- `Is this a scam or not?` — captures a fresh view of the phone, reads legible SMS text, identifies concrete warning signs, and gives cautious advice.
- `Stop.` or `Be quiet.` — cancels current playback.
- `Volume up.` or `Volume down.` — adjusts the AT-CSP1 by ten percentage points.
- `Set volume to 90 percent.` — selects an exact hardware playback level.
- `Go to sleep.` — enters a quiet idle state.
- `Wake up.` — explicitly resumes it; the next detected utterance also wakes the tactile session.

These sentences are examples, not a command grammar. The companion has no exact-phrase router: natural paraphrases and unfamiliar wording go through the same Gemma function gate, while requests requiring no hardware or live evidence receive ordinary Gemma answers.

To interrupt, do not wait for Gemma to finish. Unmute while it is speaking, say the new request, and mute again. Human voice onset terminates active playback; the newest request invalidates any older unfinished model response.

Playback defaults to 100% at each companion start. Volume requests remain available throughout the session and are semantically selected by Gemma. From a Jetson terminal, `make volume VOLUME=90` provides the same adjustment; `GEMMA_PLAYBACK_VOLUME` changes the service default.

## Recommended live-demo sequence

1. Power on with the mic muted and both USB devices attached.
2. Film the OBSBOT centering and the `Hi, I'm Gemma!` readiness greeting.
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

From the development Mac, the same restart is available without an interactive password:

```bash
make restart
```

The service installer adds a narrowly scoped sudoers rule for this exact service restart;
it does not grant general passwordless sudo. Set `GEMMA_REMOTE_HOST=user@host` to override
the default `iputra@192.168.55.1` target.

The command returns successfully only after the restarted process publishes a fresh companion
log, both local model endpoints respond, and the grounded startup greeting is recorded.

For a clean shutdown, use Ubuntu's power menu or `sudo poweroff` and wait for shutdown before disconnecting power.
