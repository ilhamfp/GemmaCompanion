"""Offline text-to-speech through eSpeak NG."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from .speaker import play_audio

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ESPEAK = REPO_ROOT / ".runtime" / "espeak" / "usr" / "bin" / "espeak-ng"


class TTSError(RuntimeError):
    """Raised when speech synthesis fails."""


def _espeak_binary() -> str:
    configured = os.environ.get("GEMMA_ESPEAK_PATH")
    if configured:
        return configured
    system = shutil.which("espeak-ng")
    if system:
        return system
    if RUNTIME_ESPEAK.is_file():
        return str(RUNTIME_ESPEAK)
    raise TTSError("espeak-ng not found; run the documented runtime bootstrap")


def synthesize(
    text: str,
    output_dir: str | os.PathLike[str] | None = None,
    *,
    words_per_minute: int = 135,
) -> str:
    clean_text = " ".join(text.split())
    if not clean_text:
        raise ValueError("text must not be empty")
    if not 80 <= words_per_minute <= 220:
        raise ValueError("words_per_minute must be between 80 and 220")

    destination = Path(output_dir or Path.cwd() / "captures" / "audio").expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"speech-{uuid.uuid4().hex}.wav"
    result = subprocess.run(
        [_espeak_binary(), "-s", str(words_per_minute), "-w", str(path), clean_text],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown espeak-ng error"
        raise TTSError(f"speech synthesis failed: {detail}")
    if not path.is_file() or path.stat().st_size <= 44:
        raise TTSError("speech synthesis produced no PCM samples")
    return str(path)


def speak(text: str, *, words_per_minute: int = 135) -> None:
    """Synthesize and play one sentence."""

    with tempfile.TemporaryDirectory(prefix="gemma-speak-") as temp_dir:
        wav_path = synthesize(text, temp_dir, words_per_minute=words_per_minute)
        play_audio(wav_path)
