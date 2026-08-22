#!/usr/bin/env python3
"""Prove that barge-in can terminate active ALSA playback promptly."""

from __future__ import annotations

import math
import struct
import sys
import tempfile
import time
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from audio.interruptible import InterruptibleSpeech  # noqa: E402


def _tone(path: Path, seconds: float = 5.0) -> None:
    sample_rate = 16_000
    frames = bytearray()
    for index in range(round(sample_rate * seconds)):
        sample = round(2_000 * math.sin(2 * math.pi * 220 * index / sample_rate))
        frames.extend(struct.pack("<h", sample))
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(frames)


def main() -> int:
    speech = InterruptibleSpeech()
    with tempfile.TemporaryDirectory(prefix="gemma-cancel-test-") as directory:
        path = Path(directory) / "tone.wav"
        _tone(path)
        speech.play_file(path)
        if not speech.speaking.wait(timeout=2):
            raise TimeoutError("test playback did not start")
        time.sleep(0.25)
        cancel_seconds = speech.interrupt()
        speech.wait(timeout=2)
    if cancel_seconds >= 0.3:
        raise AssertionError(f"playback cancellation took {cancel_seconds:.3f}s")
    if speech.speaking.is_set():
        raise AssertionError("playback remained active after cancellation")
    print("playback_started: PASS; source=5.0s generated local WAV")
    print(f"cancel_seconds: {cancel_seconds:.4f}; limit: <0.3000")
    print("playback_after_cancel: stopped")
    print("audio_saved: no; temporary test WAV removed")
    print("result: PASS active ALSA playback is physically interruptible")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
