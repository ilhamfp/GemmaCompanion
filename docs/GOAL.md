# Goal contract: implement docs/PRD.md end to end

This file is the operating contract for the agent running under `/goal`. Read it together with `docs/PRD.md` before doing anything. The PRD says **what** to build; this file says **how to work, how to prove progress, and when to stop**.

## Objective and stopping condition

Implement `docs/PRD.md` on the Jetson until the Definition of Done (PRD section 6) is met. The run is complete when:

- `docs/STATUS.md` shows M0 through M7 as `DONE` (a `FALLBACK` entry counts as DONE if the fallback's own verification passed)
- every verification script below exits 0 on the Jetson in this session
- git is clean and pushed to the public repo, and README explains the Gemma role and any fallbacks honestly
- the agent has paused at M8 with a dry-run checklist for the human to record the video and submit

## Read first, in this order

1. `docs/PRD.md` (sections 0 and 5 are non-negotiable)
2. `AGENTS.md` / `CLAUDE.md` if present
3. `docs/STATUS.md` if it exists: resume from the first milestone not marked DONE, never redo a DONE milestone

## Environment

- The agent runs on a Mac. The product runs only on the Jetson at `iputra@192.168.55.1` (key auth). First command of every session:
  `ssh -o BatchMode=yes -o ConnectTimeout=10 iputra@192.168.55.1 'hostname && id'`
- Every Jetson command goes through ssh. Label each command `MAC` or `JETSON` in reports.
- Project lives at `~/gemma-companion` on the Jetson, git-tracked. Commit at every milestone boundary with message `M<n>: <what was verified>`.

## How to work

- Checkpoints, strictly in order: M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8.
- Respect each milestone's hard time cap (PRD section 0). When a cap is hit, take that milestone's named fallback, record it in STATUS.md, move on.
- Check the clock (`date` on the Mac) at every checkpoint. Past 2:15 pm SGT with M5 not DONE: pause and ask about cutting scope. Under 75 minutes to 3:30 pm: stop all feature work, go to M8.

## What proves a milestone

Each milestone has one verification script that exits 0 on success and prints evidence. The agent creates these; they run on the Jetson.

| Milestone | Verification | Passes when |
|---|---|---|
| M0 | `scripts/recon.sh` | writes `docs/recon.md`; identified OBSBOT `/dev/video` node, AT-CSP1 ALSA card index, CUDA presence, free RAM and disk |
| M1 | `scripts/test_camera.py` | JPEG captured in under 2 s, path and dimensions printed; image scp'd to the Mac and its contents described to the human |
| M2 | `scripts/test_ptz.py` | look_left, capture, look_right, capture, look_center; the two frames differ by a mean pixel diff above a set threshold; prints method used (uvc / pyusb / digital-crop) |
| M3 | `scripts/test_audio.py` | records 3 s, transcribes, prints transcript; speaks a sentence; also exits 0 in `--text` mode |
| M4 | `scripts/test_gemma.py` | text→text, image+text→text, and a parseable tool call; prints model, quantization, runtime, per-step latency, `free -h` after load |
| M5 | `scripts/test_loop.py` | scripted scenario in which Gemma itself issued at least one `look_*` call and its next message references something only in the new frame; writes `logs/session-*.jsonl` |
| M6 | `make demo-akinator` | two consecutive full games pass (`--text` allowed); **human confirms in chat** |
| M7 | `make demo-elderly` | 3/3 glasses-found runs plus 1 honest not-found run; **human confirms in chat** |
| M8 | README.md, LICENSE, .gitignore (no weights), `make reset` works, repo pushed and public | then **pause** |

M6 and M7 need human confirmation because the agent cannot hear the speaker or see the gimbal move.

## Where to record it

`docs/STATUS.md` is the single ledger. Create it at M0. One block per milestone, exactly this shape, updated the moment a milestone passes:

```
## M2 PTZ control
status: DONE | IN_PROGRESS | FALLBACK | BLOCKED
verified_by: scripts/test_ptz.py
verified_at: 2026-08-22 11:05 SGT
evidence: <last 5 lines of real output from the verification command, verbatim>
fallback_taken: none | <what and why>
commit: <short sha>
notes: <latencies, memory, gotchas>
```

Mark DONE only after the verification command has actually run on the Jetson and exited 0 in this session. Never on the basis of reading code or expecting it to work. `docs/progress.md` stays the running command log with real output, as the PRD requires.

## Progress reports

After each checkpoint, a compact update: current milestone, what was verified (command and exit code), what is next, blocked or not. No long narration.

## Pause and ask the human (do not guess or work around)

- a command needs an interactive sudo password: print the exact command and stop
- anything that would reboot, reflash, change SSH or network settings, install drivers, or run `apt upgrade` / `dist-upgrade`
- PTZ not controllable via UVC and the 30-minute pyusb attempt failed, before switching to digital-crop
- Gemma 4 E2B with vision cannot be obtained or run inside the M4 cap, before switching to Gemma 3n E2B
- free RAM under 500 MB during inference, or disk under 10 GB
- M6 or M7 awaiting human confirmation
- past 2:15 pm SGT with M5 not DONE

## Never

Stream video into Gemma, build a dashboard or UI, commit model weights, delete files the agent did not create, touch infrastructure that already works.
