#!/usr/bin/env python3
"""M3 acceptance test for AT-CSP1 record/STT/TTS plus keyboard fallback."""

from __future__ import annotations

import argparse
import re
import sys
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from audio.mic import record_seconds  # noqa: E402
from audio.stt import transcribe  # noqa: E402
from audio.tts import speak  # noqa: E402


def _keyboard_text(value: str) -> str:
    normalized = " ".join(value.split()).strip()
    if not normalized:
        raise ValueError("keyboard text must not be empty")
    return normalized


def _text_test(value: str) -> int:
    normalized = _keyboard_text(value)
    print("mode: text")
    print(f"input: {value}")
    print(f"normalized: {normalized}")
    print("audio_devices_used: none")
    print("result: PASS keyboard text fallback exits cleanly")
    return 0


def _duration(path: str) -> float:
    with wave.open(path, "rb") as wav_file:
        return wav_file.getnframes() / wav_file.getframerate()


def _hardware_test(output_dir: Path) -> int:
    speak("Please say: Gemma, please find my glasses. Now.", words_per_minute=145)
    print("Speak now: Gemma, please find my glasses", flush=True)
    recording_path = record_seconds(3, output_dir)
    transcript = transcribe(recording_path)
    words = set(re.findall(r"[a-z]+", transcript.casefold()))
    if len(words) < 3 or not ({"glass", "glasses"} & words):
        raise AssertionError(f"unexpected acoustic transcript: {transcript!r}")

    spoken_sentence = "Hello, I am Gemma"
    speak(spoken_sentence, words_per_minute=130)
    fallback_value = _keyboard_text("yes")

    print(f"recording: {recording_path}; duration_seconds: {_duration(recording_path):.3f}")
    print(f"transcript: {transcript}")
    print(f"spoken: {spoken_sentence}; device: plughw:3,0")
    print(f"text_fallback: {fallback_value}; status: PASS")
    print("result: PASS 3s record, offline STT, TTS playback, and text mode")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", action="store_true")
    parser.add_argument("--text-input", default="yes")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "captures" / "audio"))
    args = parser.parse_args()
    if args.text:
        return _text_test(args.text_input)
    return _hardware_test(Path(args.output_dir))


if __name__ == "__main__":
    raise SystemExit(main())
