"""AT-CSP1 microphone capture with a simple pause-tolerant energy VAD."""

from __future__ import annotations

import math
import os
import subprocess
import time
import uuid
import wave
from array import array
from pathlib import Path

SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2
DEFAULT_CAPTURE_DEVICE = "plughw:3,0"


class AudioCaptureError(RuntimeError):
    """Raised when ALSA recording fails."""


def _capture_device() -> str:
    return os.environ.get("GEMMA_AUDIO_CAPTURE_DEVICE", DEFAULT_CAPTURE_DEVICE)


def _new_wav_path(output_dir: str | os.PathLike[str] | None, prefix: str) -> Path:
    destination = Path(output_dir or Path.cwd() / "captures" / "audio").expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    return destination / f"{prefix}-{uuid.uuid4().hex}.wav"


def _arecord_base(*, file_type: str) -> list[str]:
    return [
        "arecord",
        "-q",
        "-D",
        _capture_device(),
        "-t",
        file_type,
        "-f",
        "S16_LE",
        "-c",
        str(CHANNELS),
        "-r",
        str(SAMPLE_RATE),
    ]


def record_seconds(
    seconds: float,
    output_dir: str | os.PathLike[str] | None = None,
) -> str:
    """Record an exact-duration mono WAV from the AT-CSP1."""

    if seconds <= 0:
        raise ValueError("seconds must be positive")
    path = _new_wav_path(output_dir, "recording")
    command = [*_arecord_base(file_type="wav"), "-d", str(max(1, math.ceil(seconds))), str(path)]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=seconds + 5)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown arecord error"
        raise AudioCaptureError(f"ALSA recording failed: {detail}")
    if not path.is_file() or path.stat().st_size <= 44:
        raise AudioCaptureError("ALSA recording produced no PCM samples")
    return str(path)


def _rms(chunk: bytes) -> float:
    samples = array("h")
    samples.frombytes(chunk)
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


def record_until_silence(
    max_seconds: float = 8,
    output_dir: str | os.PathLike[str] | None = None,
    *,
    silence_seconds: float = 1.5,
    energy_threshold: float = 450,
) -> str:
    """Record until 1.5 s of post-speech silence or the bounded time limit.

    Audio is sampled in 100 ms chunks. Silence before the user starts does not
    terminate capture, which makes the function tolerant of conversational pauses.
    """

    if max_seconds <= silence_seconds or silence_seconds < 1.5:
        raise ValueError("max_seconds must exceed a silence threshold of at least 1.5 seconds")

    path = _new_wav_path(output_dir, "utterance")
    process = subprocess.Popen(
        _arecord_base(file_type="raw"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    frames: list[bytes] = []
    chunk_seconds = 0.1
    chunk_bytes = int(SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH * chunk_seconds)
    started = time.monotonic()
    speech_started = False
    silent_for = 0.0

    try:
        while time.monotonic() - started < max_seconds:
            chunk = process.stdout.read(chunk_bytes)
            if not chunk:
                break
            frames.append(chunk)
            if _rms(chunk) >= energy_threshold:
                speech_started = True
                silent_for = 0.0
            elif speech_started:
                silent_for += len(chunk) / (SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH)
                if silent_for >= silence_seconds:
                    break
    finally:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)

    if not frames:
        stderr = process.stderr.read().decode(errors="replace").strip() if process.stderr else ""
        raise AudioCaptureError(f"ALSA microphone returned no samples: {stderr}")

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(b"".join(frames))
    return str(path)
