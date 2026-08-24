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
6. Every completed transcript reaches Gemma's semantic function gate; no exact user phrase or direction-alias router runs first.
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
  -> GEMMA_TOOL_GATE
     -> movement tool: ACT -> semantic completion check -> READY/LISTENING
     -> inspect_view: CAPTURE -> GEMMA_VISION -> SPEAKING
     -> find/volume/stop/sleep tool: deterministic local action
     -> respond_normally: GEMMA_TEXT -> SPEAKING

SPEAKING
  -> voice onset: cancel playback -> BARGE_IN
  -> playback complete: READY/LISTENING

SLEEPING
  -> next detected utterance resumes interaction
```

## Agentic tool selection

The latest utterance wins, but it is not compared with a list of phrases. Gemma receives the newest transcript, current camera direction, and these registered capabilities:

- `look_left`, `look_right`, `look_up`, `look_down`, `look_center`
- `inspect_view`, `find_object`
- `make_voice_louder`, `make_voice_softer`, `set_volume`
- `cancel_current_response`, `sleep`
- `respond_normally`

Gemma selects from meaning and may emit more than one function for a compound request. A movement-only request ends after bounded UVC motion; movement plus a visual question receives a second tiny Gemma completion check and then captures exactly one fresh frame. If the 2B model narrates an action instead of serializing it, a fresh-context repair turn converts that intent into a registered function. If it incorrectly chooses ordinary chat for a present physical referent, a separate Gemma evidence classifier chooses `CAMERA` or `KNOWLEDGE`; this is semantic model inference, not phrase matching.

llama.cpp runs with `--skip-chat-parsing`, so its strict PEG parser cannot turn a valid tool call plus harmless trailing prose into HTTP 500. `GemmaClient` accepts only names from the supplied registry and recovers native Gemma, bare-line, and positional serialization; arbitrary text never becomes an executable action.

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
- real utterance Whisper transcription: under 1.5 seconds (observed 1.454--1.470 seconds)
- completed transcript to bounded gimbal result: under 3 seconds (observed maximum 2.139 seconds)
- fresh-image answer after transcript: under 8 seconds (observed 4.871 seconds)
- stale response after a newer utterance: never spoken
- available RAM with Gemma, Whisper, and TTS loaded: above 500 MiB

## Boot behavior

`scripts/run_companion.sh` is the service entry point. It waits for `/dev/video0` and the stable ALSA card alias `Device`, starts the local Gemma and Whisper servers if necessary, then runs the companion with the repository virtual environment when available. Gemma uses two parallel slots in a 4096-token shared context, allowing a newer turn to begin while an older turn is being invalidated. The companion checks model health every five seconds; systemd restarts it after a process failure. Logs go to the system journal plus the application JSONL session log.

The boot observation and an action-prefix warmup occupy the two Gemma slots concurrently, so the first
physical request after the greeting reuses the action-selection prefix. If the function gate emits a
complete ordinary answer directly, a second Gemma classification must confirm KNOWLEDGE before that
answer is reused; ACTION and CAMERA classifications retain the full tool or fresh-frame paths. Spoken
answers use the same Kokoro voice and text but synthesize bounded chunks one step ahead of playback,
which reduces time to first audio while preserving word order and interruption semantics.

True headless power-on startup uses `deploy/gemma-companion.service`. Installing or enabling it changes system configuration and therefore remains a one-time human-authorized sudo step. A reboot is a separate final acceptance gate.

## Native-audio experiment

The loaded Gemma 4 projector advertises audio input, and a real `Find my glasses` WAV selected `find_object` directly in 2.524 seconds without Whisper. The experiment had 2.888 GiB available and is reproducible with `scripts/experiment_direct_audio.py` on a freshly started `GEMMA_PARALLEL=1` server.

This is not the boot default. On the 8 GB Jetson, mixing native audio and later GPU vision in the same resident process can exhaust CUDA memory; using a CPU projector avoided that crash but made vision exceed the latency target. The reliable stage configuration therefore keeps Whisper for speech and GPU Gemma for reasoning/vision. `GEMMA_SPEECH_MODE=direct` remains an explicit experimental code path, not a production recommendation.

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
