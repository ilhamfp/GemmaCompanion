"""Offline speech-to-text through whisper.cpp."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_WHISPER = REPO_ROOT / ".runtime" / "whisper-bin-ubuntu-arm64" / "whisper-cli"
DEFAULT_MODEL = REPO_ROOT / "models" / "ggml-tiny.en.bin"


class TranscriptionError(RuntimeError):
    """Raised when offline transcription fails."""


def _runtime_path() -> Path:
    return Path(os.environ.get("GEMMA_WHISPER_PATH", str(RUNTIME_WHISPER))).expanduser().resolve()


def _model_path() -> Path:
    return Path(os.environ.get("GEMMA_WHISPER_MODEL", str(DEFAULT_MODEL))).expanduser().resolve()


def transcribe(wav_path: str | os.PathLike[str]) -> str:
    """Return normalized English text for a local WAV file."""

    audio_path = Path(wav_path).expanduser().resolve()
    runtime = _runtime_path()
    model = _model_path()
    for label, path in (("audio", audio_path), ("whisper.cpp runtime", runtime), ("Whisper model", model)):
        if not path.is_file():
            raise TranscriptionError(f"{label} does not exist: {path}")

    with tempfile.TemporaryDirectory(prefix="gemma-whisper-") as temp_dir:
        output_base = Path(temp_dir) / "transcript"
        command = [
            str(runtime),
            "-m",
            str(model),
            "-f",
            str(audio_path),
            "-l",
            "en",
            "-t",
            str(min(4, os.cpu_count() or 1)),
            "-nt",
            "-np",
            "-otxt",
            "-of",
            str(output_base),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=60)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown whisper.cpp error"
            raise TranscriptionError(f"whisper.cpp failed: {detail}")
        transcript_path = output_base.with_suffix(".txt")
        raw = transcript_path.read_text(encoding="utf-8") if transcript_path.is_file() else result.stdout

    transcript = re.sub(r"\[[^]]+\]", " ", raw)
    transcript = " ".join(transcript.split()).strip()
    if not transcript:
        raise TranscriptionError("whisper.cpp returned an empty transcript")
    return transcript
