"""AT-CSP1 WAV playback."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

DEFAULT_PLAYBACK_DEVICE = "plughw:3,0"


class AudioPlaybackError(RuntimeError):
    """Raised when ALSA playback fails."""


def play_audio(wav_path: str | os.PathLike[str]) -> None:
    path = Path(wav_path).expanduser().resolve()
    if not path.is_file():
        raise AudioPlaybackError(f"audio file does not exist: {path}")
    device = os.environ.get("GEMMA_AUDIO_PLAYBACK_DEVICE", DEFAULT_PLAYBACK_DEVICE)
    result = subprocess.run(
        ["aplay", "-q", "-D", device, str(path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown aplay error"
        raise AudioPlaybackError(f"ALSA playback failed: {detail}")
