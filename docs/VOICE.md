# M9: Voice upgrade (replace eSpeak NG with a natural TTS)

The voice is the spotlight of the demo. `docs/STATUS.md` shows M3 took the eSpeak NG fallback, which is why speech sounds robotic. This milestone replaces it with a natural neural TTS while keeping every other milestone untouched. All PRD section 0 and GOAL.md rules still apply.

## Current state (verified from the repo, do not re-discover)

- `audio/tts.py` shells out to `espeak-ng` via `subprocess` per sentence and returns a WAV path; `speak(text, words_per_minute=135)` synthesizes then calls `audio/speaker.py:play_audio`, which runs `aplay -D plughw:3,0`. `plughw` already resamples, so any TTS sample rate (24 kHz, 44.1 kHz) plays correctly.
- Nothing is installed with pip except Pillow. Runtime binaries live under `.runtime/` (gitignored). `.venv/` is already gitignored, so a venv is the intended home for Python packages.
- Gemma runs on the GPU via llama.cpp. After the full M7 sequence, 2.8 GiB RAM was available. Budget for TTS: at most 800 MiB resident, and it must run on CPU so it never contends with Gemma for the GPU.
- Python 3.12, aarch64, no sudo. Any install must be user-space only.

## Target

`speak()` sounds like a calm human, not a synthesizer, and the "Let me look over there" moment plays with no audible wait.

## Candidates, in the order to try (take the first that passes the gate)

### Option A: Kokoro-82M via `kokoro-onnx` (primary)
Apache 2.0, 82M params, best naturalness in its size class, proven on Orin Nano.
```
python3 -m venv .venv && . .venv/bin/activate
pip install --upgrade pip
pip install kokoro-onnx soundfile numpy
# model + voices (~330 MB total), into models/ (gitignored):
#   kokoro-v1.0.onnx and voices-v1.0.bin from the kokoro-onnx GitHub releases
```
Use `onnxruntime` CPU (the default dependency; do not chase onnxruntime-gpu on Jetson). Voice shortlist to audition: `af_heart`, `af_bella`, `am_michael`, `bm_george`. Speed 1.0 for Akinator, 0.9 for elderly mode. Output is 24 kHz mono.

### Option B: Kyutai Pocket TTS (if A fails the gate)
100M params, CPU-first, streaming, ~200 ms to first audio, stock PyTorch (CPU wheel, no CUDA build).
```
pip install pocket-tts   # downloads weights on first load
```
If this also fails to install within the cap, try the single-file C++ runtime PocketTTS.cpp (ONNX Runtime, has a CLI and HTTP server), which fits the existing "binaries under .runtime/" pattern.

### Option C: keep eSpeak NG
Only if A and B both miss their caps. Record the reason.

## Install gate (applies to A and B)

- Hard cap: 25 minutes per option from first command to a playable WAV. If it is not producing audio by then, move to the next option.
- Do not install torch with CUDA, do not build anything from source for more than 10 minutes, do not touch system Python.
- Check `free -h` after loading the model; if available RAM drops below 2.0 GiB with Gemma loaded, abandon the option.

## Required implementation (audio/tts.py)

Keep the public surface used by the rest of the repo so nothing else changes:

```python
speak(text: str, *, words_per_minute: int = 135) -> None   # keep signature; map wpm to model speed
synthesize(text, output_dir=None, *, words_per_minute=135) -> str   # keep
```
Add:
```python
class TTSEngine:                      # loaded ONCE per process, reused by every call
    def synth(self, text, speed=1.0) -> (np.ndarray, int)
prerender(phrases: list[str]) -> dict[str, str]   # text -> cached wav path, called at session start
speak_cached(key) -> None               # plays a pre-rendered clip, non-blocking option
```
Rules:
1. **Resident model.** Load on first use and keep it in a module-level singleton. No subprocess per sentence.
2. **Pre-render the fixed lines** at session start in both demos. Find every fixed string the loop speaks (look in `agent/prompts.py`, `agent/loop.py`, `demos/*.py`) and pre-render them: the look announcement ("Let me look over there."), the confirmation ("You want me to find your glasses, is that right?"), "One moment.", and the elderly not-found line. Play the look announcement **concurrently with the gimbal move** (start playback in a thread, then call `look_*`).
3. **Playback queue.** One playback worker; `speak` enqueues, the mic must never open while the queue is non-empty. Expose `wait_until_silent()` and call it before `record_seconds`.
4. **Sentence split.** If a Gemma reply has more than one sentence, synthesize and enqueue sentence by sentence so the first one starts playing while the rest render.
5. **Speech-friendly text.** Strip markdown, bullets, and emoji before synthesis; expand digits to words for short numbers. Add one line to the Gemma system prompts in `agent/prompts.py`: "Reply in plain spoken English, short sentences, normal punctuation, no lists or markdown."
6. **Fallback.** If the engine fails to load at runtime, fall back to eSpeak NG and log a WARNING, so the demo never dies because of the voice.
7. Keep eSpeak NG installed; kokoro-onnx's phonemizer may need the espeak-ng shared library. Point it at `.runtime/espeak` via env if the default lookup fails.

## Audition (human in the loop, 10 minutes max)

Script `scripts/audition_tts.py` renders these three lines in each candidate voice into `artifacts/audition/<voice>-<n>.wav`:
1. "I'm not sure yet. Let me look over there."
2. "Your glasses are on the table beside the sofa."
3. "I couldn't find the red umbrella from here. Please check its usual place."

scp the folder to the Mac and pause; the human picks a voice and speed and replies in chat. Default to `af_heart` at speed 1.0 if no reply within the cap.

## Verification: `scripts/test_tts.py` (exit 0 = pass)

Prints and checks, on the Jetson:
- `engine:` name, version, voice, sample rate
- `load_seconds:` model load time (one-time)
- `first_audio_seconds:` time from `speak()` call to first PCM sample for the 12-word sentence "Your glasses are on the table beside the sofa, next to the cup." Must be **under 1.5 s warm**.
- `total_seconds:` full synthesis for that sentence, must be **under 3.0 s**.
- `cached_play_seconds:` time to start playing a pre-rendered clip, must be **under 0.2 s**.
- `free_available_gib:` with Gemma server running, must be **above 2.0**.
- writes the test WAV to `artifacts/tts-sample.wav` for the human to scp and listen.
- `result: PASS ...` or a clear FAIL line.

Then re-run `scripts/test_audio.py` (M3) to confirm record/STT/TTS still passes with the new engine, and run one `make demo-akinator` game to confirm the look announcement plays during the move.

## Record it

Add to `docs/STATUS.md`:
```
## M9 Voice upgrade
status: DONE | FALLBACK | BLOCKED
verified_by: scripts/test_tts.py, scripts/test_audio.py, make demo-akinator
verified_at: <SGT from Mac clock>
evidence: <last lines of test_tts.py output verbatim>
engine: <kokoro-onnx af_heart 1.0 | pocket-tts ... | espeak-ng>
fallback_taken: none | <which option and why>
commit: <sha>
notes: <what the human said in the audition, memory after load>
```
Update the M3 block's `notes` with a one-line pointer to M9. Update README: replace "eSpeak NG fallback" in the architecture diagram and add the engine, license, and measured first-audio latency to the table. Add the install commands to the one-time setup section. Re-record `docs/demo-checklist.md` if any command changed.

## Pause and ask the human

- Any sudo prompt.
- Audition results ready (scp'd) for voice selection.
- Both A and B missed their caps (before settling on C).
- It is past 2:30 pm SGT and M9 is not verified: stop, revert `audio/tts.py` to the committed eSpeak version with `git checkout`, and report.
