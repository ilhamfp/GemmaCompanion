# M8 human demo-video handoff

The human records and submits the video. Keep the final cut at or below 3:00.

## Before recording

- Place 6–10 recognizable Akinator objects in the room. Use `laptop` as the reliable target and keep at least one object outside the initial view.
- Leave the white Audio-Technica tabletop speaker in the verified far-left/tabletop view.
- Frame the phone so the OBSBOT gimbal and AT-CSP1 are visible.
- On the Jetson:

  ```bash
  cd ~/gemma-companion
  make reset
  make runtime
  ```

- The human turns off Wi-Fi after setup, without disturbing USB Ethernet:

  ```bash
  nmcli radio wifi off
  ```

- Confirm `make reset` reports `(0.0, 0.0)`. Do one off-camera dry run of each demo.

## Recording timeline

### 0:00–0:15 — premise and offline proof

- Say: “Gemma Companion is an on-device AI companion that can see, hear, speak, and look for itself.”
- Show Wi-Fi off on the Jetson.
- Say: “When Gemma doesn't know, it doesn't ask for another picture. It looks.”

### 0:15–1:30 — Real-Life Akinator

```bash
make reset
make demo-akinator
```

- Think of the laptop.
- Keep the gimbal in frame when Gemma says “Let me look over there.” and moves; the cached natural-voice line should already be playing as the camera starts.
- Answer only `yes`, `no`, or `not sure`.
- End immediately after the correct guess.

If the room is noisy, use `make demo-akinator DEMO_ARGS=--text` and type the answers while retaining spoken output.

### 1:30–2:30 — requested-object finder

```bash
make reset
make demo-elderly
```

- Capture Gemma confirming the Audio-Technica request.
- Keep the physical movement in frame.
- Capture the plain location: the white tabletop.

### 2:30–3:00 — how it works

- Show the architecture diagram in `README.md`.
- In a second terminal, show the latest tool evidence:

  ```bash
  tail -n 12 "$(ls -t logs/session-*.jsonl | head -1)"
  ```

- Point out `GEMMA_LOOK_DECISION`, `LOOK_ANNOUNCEMENT_OVERLAP`, `LOOK`, the fresh `OBSERVE`, and `FINDER_RESULT`/`GAME_RESULT`.
- Say: “Gemma 4 E2B Q4_0 runs locally on the 8 GB Jetson; no image or audio leaves the device.”

## Submission metadata

- Project name: **Gemma Companion**
- One-liner: **An on-device AI companion that can see, hear, speak, and look for itself.**
- Primary track: **Best Use of Gemma**
- Secondary track: **Best Elderly Hack**
- Repository: <https://github.com/ilhamfp/GemmaCompanion>

After recording, restore Wi-Fi if desired:

```bash
nmcli radio wifi on
```

Final human checks: video ≤3:00, camera movement visible, speech audible, offline proof visible, repo link opens, both tracks selected, submission completed before 3:30 pm SGT.
