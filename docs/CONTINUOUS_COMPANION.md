# Continuous companion and physical barge-in

## Outcome

After a one-time service installation, powering the Jetson starts one offline companion session. The OBSBOT centers and captures a fresh frame, Gemma announces that it is ready, and the AT-CSP1 capture stream remains open. The human normally leaves the physical microphone muted, unmutes to speak or interrupt, and mutes again to end the utterance.

No wake word, Mac, network connection, keyboard, or dashboard is required during the live interaction.

## Interaction contract

1. Muted PCM is continuously consumed but never stored.
2. Human voice onset while unmuted cancels current speaker playback immediately.
3. A short in-memory pre-roll preserves the beginning of the command.
4. Returning to the muted noise floor closes the utterance quickly.
5. Only the completed utterance is written to a temporary WAV for offline Whisper transcription; it is deleted immediately afterward.
6. Physical commands bypass Gemma and dispatch directly to bounded UVC controls.
7. A visual question always captures a fresh still at the current physical direction before Gemma answers.
8. A newer utterance invalidates any older inference or synthesized response. Stale output is discarded.

## State machine

```text
BOOTING
  -> wait for camera + AT-CSP1
  -> start Gemma
  -> center + fresh capture
  -> READY/LISTENING

READY/LISTENING
  -> voice onset: BARGE_IN (cancel speech, invalidate prior turn)
  -> mute/silence: TRANSCRIBE
  -> direct movement: ACT -> READY/LISTENING
  -> visual question: CAPTURE -> GEMMA_VISION -> SPEAKING
  -> other request: GEMMA_TEXT -> SPEAKING

SPEAKING
  -> voice onset: cancel playback -> BARGE_IN
  -> playback complete: READY/LISTENING

SLEEPING
  -> only "wake up" is acted on
  -> capture stays local and no model request runs
```

## Deterministic command priority

The latest utterance wins. Commands are matched in this order:

1. `stop`, `cancel`, `be quiet`
2. `go to sleep`, `wake up`
3. `look left`, `look right`, `look up`, `look down`, `look center`
4. `what do you see`, `describe what you see`, `what is in front of you`
5. all other text goes to the local Gemma conversation path

Movement commands never wait for Gemma. Camera access is serialized, and every movement is clamped by the existing OBSBOT safety bounds.

## Audio thresholds

The physical-button probe kept the ALSA stream connected throughout mute transitions. Measured 250 ms windows were approximately 19--253 RMS muted, 273--516 RMS unmuted ambient, and 3973 RMS at speech onset.

Initial defaults:

- 16 kHz, 16-bit mono, 100 ms processing windows
- 300 ms in-memory pre-roll
- speech onset: two consecutive windows at or above 700 RMS
- utterance end: four consecutive windows at or below 350 RMS
- maximum utterance: 12 seconds

All thresholds are environment-overridable and must be tuned only through the physical verifier, not by saving ambient audio.

## Latency gates

- voice onset to current playback cancellation: under 300 ms
- mute/end-of-speech to completed segment: under 600 ms
- completed `look_*` utterance to gimbal command: under 1.5 seconds, including Whisper
- fresh-image Gemma response: under 5 seconds after transcription
- stale response after a newer utterance: never spoken
- available RAM with Gemma, Whisper, and TTS loaded: above 500 MiB

## Boot behavior

`scripts/run_companion.sh` is the service entry point. It waits for `/dev/video0` and the stable ALSA card alias `Device`, starts the local Gemma server if necessary, then runs the companion with the repository virtual environment when available. The service restarts on failure and writes logs to the system journal plus the application JSONL session log.

True headless power-on startup uses `deploy/gemma-companion.service`. Installing or enabling it changes system configuration and therefore remains a one-time human-authorized sudo step. A reboot is a separate final acceptance gate.

## Verification order

1. Pure command-parser, cancellation-generation, WAV, and state tests on the Mac.
2. Jetson foreground verifier with text injection: all physical directions, fresh visual answer, stale-response suppression, memory guard.
3. Jetson automatic playback-cancellation test.
4. Human physical barge-in: mute, start long speech, unmute and say `look left`, mute; confirm speech stops and gimbal moves.
5. Human follow-up: ask `what do you see`, then interrupt its answer with `look right`.
6. Install and start the system service; confirm readiness without SSH interaction.
7. With explicit human approval, power-cycle once and repeat the two-command physical acceptance without a Mac.

## Failure behavior

- Missing camera or AT-CSP1: wait and retry rather than crash-looping rapidly.
- Gemma not ready: retain listening and speak a short local error only when playback is available.
- STT error or empty transcript: discard the turn and return to listening.
- Low memory: refuse inference but preserve direct PTZ and stop commands.
- TTS failure: print/log the response and retain listening.
- Service failure: systemd restarts it after three seconds.
