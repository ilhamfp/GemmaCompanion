#!/usr/bin/env python3
"""Render the M9 human voice audition set."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from audio.tts import TTSEngine, _write_wav  # noqa: E402

VOICES = ("af_heart", "af_bella", "am_michael", "bm_george")
LINES = (
    "I'm not sure yet. Let me look over there.",
    "Your glasses are on the table beside the sofa.",
    "I couldn't find the red umbrella from here. Please check its usual place.",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "artifacts" / "audition"))
    args = parser.parse_args()
    if not 0.5 <= args.speed <= 2.0:
        raise ValueError("speed must be between 0.5 and 2.0")

    destination = Path(args.output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for voice in VOICES:
        engine = TTSEngine(voice=voice, base_speed=args.speed)
        for index, line in enumerate(LINES, start=1):
            audio, sample_rate = engine.synth(line)
            path = destination / f"{voice}-{index}.wav"
            _write_wav(path, audio, sample_rate)
            print(f"rendered: {path}; voice={voice}; speed={args.speed}; line={index}")
    print(f"result: PASS {len(VOICES) * len(LINES)} audition clips rendered at speed {args.speed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
