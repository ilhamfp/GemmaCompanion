# Gemma Companion: PRD for the build agent

> **One line:** An on-device AI companion that can see, hear, speak, and look for itself.
> **Pitch line for the demo:** When Gemma doesn't know, it doesn't ask you for another picture. It looks.

This document is the single source of truth for the agent. Work through the milestones **in order**, verify each one on the real hardware, and do not skip ahead. The hackathon is **today (Sat 22 Aug 2026)** with a **hard 3:30 pm SGT submission deadline**, so every decision below is biased toward "working and demoable" over "elegant."

---

## 0. Operating rules (read first, non-negotiable)

### Environment
- You are running on a **MacBook Pro**. The Mac is the dev machine only. It is **not** part of the AI system.
- The AI system runs entirely on an **NVIDIA Jetson Orin Nano Super (8GB, aarch64, L4T R39.2.1, Ubuntu 24.04)** reachable over USB networking.
- SSH target: `iputra@192.168.55.1`, key auth already configured. Test with:
  `ssh -o BatchMode=yes -o ConnectTimeout=10 iputra@192.168.55.1 'hostname && id'`
- Run every Jetson command via `ssh iputra@192.168.55.1 '<command>'`. Always say clearly whether a command ran on the Mac or on the Jetson.
- The user is in the `sudo` group but sudo may prompt for a password. If a command needs interactive sudo, **stop and tell the user the exact command**. Do not guess or retry with tricks.
- Inspect before changing. Never: reflash, reboot, power off, modify SSH or network settings, do broad package upgrades (`apt upgrade`, `apt dist-upgrade`), or delete files you did not create.
- Keep the project in `~/gemma-companion` on the Jetson, with a git repo. Commit after every milestone.
- Treat the device as an **Orin Nano** even if docs or the user say "Jetson Nano."

### Hackathon rules that shape the build
- **New work only.** Hardware and OS setup done before today is fine; all application code must be written today. Do not copy in a pre-existing app.
- Gemma must be **essential** to the product, not a swappable chatbot backend. The thing that proves this is: Gemma emits tool calls that physically move the camera.
- Submission needs: public GitHub repo, demo video ≤ 3:00, project name, one-line description, tracks (**Best Use of Gemma** primary, **Best Elderly Hack** secondary).
- Avoid the "what not to build" list: this must not read as an image analyzer, chatbot, or dashboard. Any debug UI must stay secondary and unpolished; do not spend time on it.

### Time budget (adjust to the clock, but keep the ratios)
| Phase | Target | Hard cap |
|---|---|---|
| M0 Recon | 20 min | 30 min |
| M1 Camera capture | 20 min | 40 min |
| M2 PTZ control | 45 min | 90 min (then use fallback) |
| M3 Audio I/O | 30 min | 45 min |
| M4 Gemma running (text, then image, then tools) | 60 min | 90 min (then use fallback model) |
| M5 Agent loop | 45 min | 60 min |
| M6 Akinator demo | 45 min | 60 min |
| M7 Glasses finder demo | 30 min | 40 min |
| M8 README + video + submit | **60 min reserved, untouchable** | |

**If a milestone hits its hard cap, take its fallback and move on.** Report the fallback to the user. At any point, if less than 75 minutes remain before 3:30 pm, stop feature work and go straight to M8 with whatever works.

---

## 1. Product summary

### The idea
Instead of a human pointing a camera at something and asking an AI what it sees, Gemma Companion gives Gemma **control over its own perception**. Gemma recognizes it lacks information, physically rotates the OBSBOT camera, captures a new frame, updates its world model, and continues reasoning. Voice in, voice out, nothing leaves the device.

### Two demos, one system
Both demos are the **same agent, same tools, same model**, with different goal prompts.

**Demo 1: Real-Life Akinator (Best Use of Gemma)**
User: "I'm thinking of something in this room. Guess what it is."
Gemma scans the room, builds a candidate list, asks yes/no questions, and when unsure says "Let me look over there," rotates the camera, and continues until it guesses.
The killer moment: **the camera physically turns on Gemma's own decision.**

**Demo 2: Glasses Finder (Best Elderly Hack)**
User: "Gemma, where did I leave my glasses?"
Gemma sweeps the room with the camera, finds the glasses, and says in plain speech: "Your glasses are on the table beside the sofa."
Narrative link: Demo 1 finds what you're thinking of; Demo 2 finds what you've forgotten.

### Why Gemma (what the demo must make visible)
1. Runs fully offline on an 8GB edge device. **The video must show Wi-Fi disconnected** (`nmcli radio wifi off` is fine, or physically unplug; the USB link to the Mac is unaffected).
2. Native function calling drives the physical camera.
3. Quantization choice (E2B Q4, roughly 3GB) is what makes this fit on the Orin Nano. Say this in the README.

---

## 2. Hardware inventory

| Device | Role | Expected Linux interface |
|---|---|---|
| Jetson Orin Nano Super 8GB | Entire runtime | host |
| Transcend 500GB NVMe | Root + models | already the boot disk |
| OBSBOT Tiny SE | Eyes (UVC video) + neck (pan/tilt gimbal) | `/dev/video*` via UVC; PTZ via UVC camera-terminal controls (`v4l2-ctl`) |
| Audio-Technica AT-CSP1 | Mic + speaker | ALSA USB audio card (`arecord -l`, `aplay -l`) |
| MacBook Pro | Dev only | SSH over USB, 192.168.55.100 ↔ 192.168.55.1 |

**Memory budget on the Jetson (8GB unified, shared CPU/GPU):** target ≤ 3.5GB for Gemma weights + KV cache, ≤ 0.5GB STT, ≤ 0.2GB TTS, rest for OS and capture. Check with `free -h` after each component is loaded and record it in `docs/memory-budget.md`.

---

## 3. Milestones, acceptance criteria, and fallbacks

Each milestone must end with (a) a runnable script under the repo, (b) the verification command and its real output pasted into `docs/progress.md`, (c) a git commit.

### M0: Recon (no changes to the system)
Run on the Jetson and record output:
```
hostname && id && uname -a && cat /etc/nv_tegra_release
free -h && df -h / && nproc
nvidia-smi 2>/dev/null || true; ls /usr/local/cuda* 2>/dev/null; dpkg -l | grep -i -E 'nvidia-jetpack|cuda-toolkit|tensorrt' | head
python3 --version && pip3 --version 2>/dev/null
which v4l2-ctl ffmpeg ollama arecord aplay gst-launch-1.0 docker 2>/dev/null
v4l2-ctl --list-devices
v4l2-ctl -d /dev/video0 --list-ctrls-menus   # repeat for each video node
arecord -l && aplay -l
lsusb
```
**Accept:** a written `docs/recon.md` stating: CUDA version present, Python version, which `/dev/videoN` is the OBSBOT, whether pan/tilt controls are exposed, the ALSA card index for the AT-CSP1, free RAM and disk.
**Decision point:** pick the Gemma runtime for M4 based on what is installed (see M4).

### M1: Camera capture
Target API: `from camera.capture import capture_image; path = capture_image()` returns a JPEG path (resize to ≤ 1024px on the long edge to keep Gemma's vision cost down).
Implementation preference: OpenCV `cv2.VideoCapture` on the OBSBOT node with MJPEG. If OpenCV is missing or broken, use `ffmpeg -f v4l2 -i /dev/videoN -frames:v 1` or GStreamer.
**Accept:** a fresh JPEG is written in under 2 s, and you `scp` it to the Mac and describe what is in it, so the user can confirm the view is right. Handle the "camera still warming up" problem by discarding the first few frames.

### M2: PTZ control (highest-risk component; do this before Gemma)
Target API in `camera/obsbot.py`:
```python
look_left(); look_right(); look_up(); look_down(); look_center()
look_at(pan_deg, tilt_deg)
```
Approach, in order:
1. UVC controls: `v4l2-ctl -d /dev/videoN --set-ctrl=pan_absolute=<v>` and `tilt_absolute`. Inspect the min/max/step from `--list-ctrls`. Units are typically 1/3600 degree; verify empirically. Also try `pan_relative`/`tilt_relative` if present.
2. If controls are listed but setting them fails with permission errors, check `ls -l /dev/videoN` and group membership (`video`). Report if sudo is needed.
3. Fallback A (if no UVC PTZ control exists): try `uvcdynctrl` or sending UVC control requests via `pyusb` to the camera terminal (CT_PANTILT_ABSOLUTE_CONTROL, selector 0x0D). Cap this at 30 minutes.
4. **Fallback B (accept and move on):** "digital look." Capture at full resolution and crop left/center/right thirds so the agent loop still has `look_*` tools. The demo loses the physical rotation moment but the architecture is unchanged. Tell the user immediately if you land here.
**Accept:** `look_left()` then `capture_image()` and `look_right()` then `capture_image()` produce visibly different frames, with a settle delay (start at 1.0 s, tune down) so frames are not motion-blurred. `look_center()` returns to a consistent home position. Movements must be bounded so the gimbal never hits its limits repeatedly.

### M3: Audio I/O
Target API in `audio/`:
```python
record_until_silence(max_seconds=8) -> wav_path   # simple energy-based VAD, tolerant of pauses
play_audio(wav_path)
speak(text)          # TTS then play
transcribe(wav_path) -> str
```
- Capture/playback: `arecord`/`aplay` with the AT-CSP1 card index, or `sounddevice` if available. 16 kHz mono for STT.
- STT: `faster-whisper` (tiny or base, int8) or `whisper.cpp`. Keep it small; latency matters more than accuracy here.
- TTS: `piper` with one clear English voice (slow it slightly for the elderly demo). Fallback: `espeak-ng`, which is ugly but works.
- Note: Gemma 4 E2B reportedly accepts native audio. **Do not depend on it.** Use the STT/TTS pipeline first; only swap in native audio in M8 polish if everything else is done.
**Accept:** say a sentence, get the transcript back; `speak("Hello, I am Gemma")` is audible from the AT-CSP1. Add a **keyboard text fallback** (`--text` flag) so every demo can run without the mic if the room is noisy.

### M4: Gemma on the Jetson
Model: **Gemma 4 E2B, 4-bit quantized** (target ~3GB). Do not start with E4B or 12B.
Runtime, pick the first that works:
1. **Ollama** if installed or installable with CUDA on this L4T (check `ollama --version` and that it reports a GPU). Confirm the model tag supports images and tool calling.
2. **llama.cpp** built with CUDA (`-DGGML_CUDA=ON`) using a GGUF plus the mmproj vision projector, served via `llama-server` with the OpenAI-compatible API.
3. Fallback: if a Gemma 4 E2B GGUF with vision is not obtainable in time, use **Gemma 3n E2B** (same size class, vision + audio) and state this honestly in the README. Gemma is still the brain; the track requirement is met.
Verify in three steps and record latency for each:
- `text -> text`: a short prompt, measure tokens/s.
- `image + text -> text`: send a captured frame, ask "List the objects you can see." Measure wall time. **If over 20 s per image, reduce image size (768px, then 512px) before anything else.**
- `tools`: provide the tool schema and confirm the model emits a parseable tool call. If native tool calling is flaky in the runtime, fall back to a strict JSON-only system prompt (`{"action": "look_right"}` etc.) parsed by your own code. This is fine and common.
Wrap it in `agent/gemma.py` with one function: `step(messages, images, tools) -> (text, tool_calls)`.
**Accept:** all three steps work from a single Python script, with measured latencies in `docs/progress.md`, and `free -h` shows the headroom.

### M5: The agent loop
`agent/loop.py` implements:
```
observe (capture) -> Gemma thinks -> one of {ASK, LOOK, ANSWER/GUESS}
LOOK -> move camera -> settle -> capture -> back to Gemma
ASK  -> speak question -> listen -> back to Gemma
```
Design constraints that make this work on an Orin Nano:
- **Never stream video into Gemma.** One frame per observation, on Gemma's request.
- **Bounded loop:** max 8 tool calls per session, max 12 questions. Force a final answer after that.
- **Room scan first:** at the start of both demos, do a fixed sweep (left, center, right) capturing 3 frames, and have Gemma produce a compact **object inventory with locations** as text. After that, Gemma reasons mostly over text and only calls `look_*` when it decides it needs to re-check. This cuts vision calls from "every turn" to "a few" and is the single biggest latency and reliability win.
- Keep a short textual memory of observed objects and which directions were already inspected; pass it back into every step.
- Log every step (timestamp, action, latency) to `logs/session-<ts>.jsonl`. This log is what you show in the video's "how it works" section.
Tools exposed to Gemma (deterministic, your code, not the SDK): `capture_image`, `look_left`, `look_right`, `look_up`, `look_down`, `look_center`, `ask_user(question)`, `say(text)`, `final_answer(text)`.
**Accept:** a run where Gemma, without being told to, calls `look_right` (or `look_left`), a new frame is captured, and its next message references something only visible in the new frame.

### M6: Akinator demo (`demos/akinator.py`)
System prompt (adapt wording, keep the constraints):
```
GOAL: Determine which physical object in this room the user is thinking of.
YOU MAY: inspect your current view; move your camera and look again; ask concise yes/no questions; remember objects and directions already checked; eliminate candidates.
DO NOT: ask the human to move the camera; ask the human to show you the object; guess before you have evidence.
When you need to see more, say briefly where you will look, then call the tool.
Ask at most one question at a time. Keep every spoken line under 20 words.
```
Reliability tricks:
- Seed the room with 6 to 10 distinct, easily recognizable objects (mug, book, bottle, plant, laptop, bag, glasses, phone, keys, fruit). Place some so they are only visible after rotating. This guarantees a "let me look over there" moment.
- Accept "yes/no/not sure" only, normalize transcripts (e.g. "yeah", "nope").
- Win condition: Gemma says a guess and the user says yes. Cap at 12 questions then force a best guess.
**Accept:** 2 consecutive successful games end to end with voice (or text fallback), each under ~3 minutes, with at least one physical camera move.

### M7: Glasses finder demo (`demos/elderly.py`)
Same loop, different prompt:
```
GOAL: Help the user find an everyday object they have misplaced.
Search systematically: center, left, right, then up/down. Remember where you have already looked.
When found, say where it is in plain, simple words, relative to furniture ("on the table beside the sofa").
If not found after searching everywhere, say so honestly and suggest one place to check. Never invent a location.
Speak slowly, one short sentence at a time, and confirm you understood the request before searching.
```
Elderly track judging is 40% empathy/usability, 30% safety/reliability, 30% impact. So:
- Voice-first, no screen needed. Confirm the request back ("You want me to find your glasses, is that right?").
- Tolerate pauses: VAD silence threshold ≥ 1.5 s.
- Safety boundaries baked into the prompt and README: it **locates** objects only; it never gives medical advice, never comments on medication dosage or timing, never claims emergencies. If the user asks something medical, it says it can't help with that and suggests asking a caregiver or doctor.
- Honest uncertainty: "I can't see them from here" is a valid answer.
**Accept:** glasses placed out of the initial view, Gemma rotates, finds them, and reports the location correctly in 3 of 3 tries. Also one negative test: glasses absent, Gemma says it could not find them.

### M8: Ship (60 minutes, untouchable)
1. **README** (`README.md`): one-line description, the three pitch lines, how Gemma is used (model, quantization, runtime, tool calling, measured latency), architecture diagram (ASCII is fine), hardware list, how to run both demos, what was live vs scripted in the video, safety/privacy boundaries for the elderly demo, and any fallbacks taken (be honest). Add a LICENSE (MIT).
2. **Public GitHub repo**: push from the Jetson or the Mac. Verify it opens in an incognito window. Do not commit model weights; add a `models/` entry to `.gitignore` with download instructions.
3. **Demo video ≤ 3:00**, recorded on the user's phone, structure:
   - 0:00–0:15 pitch line + show Wi-Fi turned off on the Jetson
   - 0:15–1:30 Akinator game, make sure the camera rotation is in frame and audible ("Let me look over there")
   - 1:30–2:30 Glasses finder
   - 2:30–3:00 15-second "how it works": the agent loop diagram and a glance at the JSONL log showing tool calls
   The user records the video; your job is to have a `make demo-akinator` / `make demo-elderly` command that starts cleanly, a `make reset` that re-centers the camera and clears state, and to do a dry run with the user before recording.
4. Submit: project name **Gemma Companion**, one-liner **"An on-device AI companion that can see, hear, speak, and look for itself."**, tracks: Best Use of Gemma + Best Elderly Hack.

---

## 4. Repo layout
```
gemma-companion/
├── README.md  LICENSE  Makefile  requirements.txt  .gitignore
├── main.py                  # --mode akinator|elderly, --text for keyboard fallback
├── agent/   gemma.py  prompts.py  loop.py  memory.py
├── camera/  capture.py  obsbot.py
├── audio/   mic.py  speaker.py  stt.py  tts.py
├── tools/   registry.py     # tool schemas + dispatch to camera/audio
├── demos/   akinator.py  elderly.py
├── scripts/ recon.sh  test_camera.py  test_ptz.py  test_audio.py  test_gemma.py
├── docs/    recon.md  progress.md  memory-budget.md
└── logs/
```
The two demos must not duplicate the loop; they differ only in prompt and a couple of config values.

---

## 5. When to stop and ask the user
- Any command needs an interactive sudo password.
- PTZ control is not exposed by UVC and the 30-minute fallback attempt failed (before switching to digital look).
- Gemma 4 E2B with vision cannot be obtained or run within the M4 cap (before switching to Gemma 3n).
- Anything that would require reboot, network changes, driver installs, or a large package upgrade.
- A disk or memory situation that looks unsafe (free RAM under 500MB during inference, disk under 10GB).
- It is 2:15 pm and a milestone past M5 is not done: ask whether to cut scope to a single demo.

For everything else, decide, act, verify on the hardware, and keep a running `docs/progress.md` with the commands run, real output, latencies, and the current status of each milestone.

---

## 6. Definition of done
- [ ] `make demo-akinator` runs a full voice game with at least one Gemma-initiated camera move
- [ ] `make demo-elderly` finds glasses that were out of the initial view and reports the location in plain speech
- [ ] Both work with Wi-Fi off on the Jetson
- [ ] `--text` fallback works for both demos
- [ ] Latencies and memory figures recorded in docs
- [ ] Public GitHub repo opens without login, README explains the Gemma role and any fallbacks
- [ ] Demo video ≤ 3:00 recorded and submitted before 3:30 pm with name, one-liner, and two tracks
