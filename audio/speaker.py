"""AT-CSP1 WAV playback."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable

DEFAULT_PLAYBACK_DEVICE = "plughw:3,0"


class AudioPlaybackError(RuntimeError):
    """Raised when ALSA playback fails."""


def play_audio(
    wav_path: str | os.PathLike[str],
    *,
    on_start: Callable[[], None] | None = None,
) -> None:
    path = Path(wav_path).expanduser().resolve()
    if not path.is_file():
        raise AudioPlaybackError(f"audio file does not exist: {path}")
    device = os.environ.get("GEMMA_AUDIO_PLAYBACK_DEVICE", DEFAULT_PLAYBACK_DEVICE)
    process = subprocess.Popen(
        ["aplay", "-q", "-D", device, str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if on_start:
        on_start()
    try:
        stdout, stderr = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        raise AudioPlaybackError("ALSA playback timed out")
    if process.returncode != 0:
        detail = stderr.strip() or stdout.strip() or "unknown aplay error"
        raise AudioPlaybackError(f"ALSA playback failed: {detail}")
