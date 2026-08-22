"""Adjust the AT-CSP1 hardware playback mixer without restarting the session."""

from __future__ import annotations

import os
import re
import subprocess
import threading

DEFAULT_AUDIO_CARD = "Device"
DEFAULT_MIXER = "PCM"
DEFAULT_PLAYBACK_VOLUME = 100
VOLUME_STEP = 10

_MIXER_LOCK = threading.Lock()


class VolumeError(RuntimeError):
    """Raised when the USB speaker mixer cannot be read or changed."""


def _card() -> str:
    return os.environ.get("GEMMA_AUDIO_CARD", DEFAULT_AUDIO_CARD)


def _run(*arguments: str) -> str:
    result = subprocess.run(
        ["amixer", "-c", _card(), *arguments],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown amixer error"
        raise VolumeError(f"AT-CSP1 mixer command failed: {detail}")
    return result.stdout


def get_volume() -> int:
    """Return the current AT-CSP1 PCM playback percentage."""

    with _MIXER_LOCK:
        output = _run("sget", DEFAULT_MIXER)
    match = re.search(r"Playback\s+\d+\s+\[(\d+)%\]", output)
    if match is None:
        raise VolumeError("AT-CSP1 PCM playback percentage was not reported")
    return int(match.group(1))


def set_volume(percent: int) -> int:
    """Set and read back a 0--100 AT-CSP1 hardware playback percentage."""

    requested = int(percent)
    if not 0 <= requested <= 100:
        raise ValueError("playback volume must be between 0 and 100")
    with _MIXER_LOCK:
        _run("sset", DEFAULT_MIXER, f"{requested}%", "unmute")
        output = _run("sget", DEFAULT_MIXER)
    match = re.search(r"Playback\s+\d+\s+\[(\d+)%\]", output)
    if match is None:
        raise VolumeError("AT-CSP1 PCM playback percentage was not reported after setting it")
    return int(match.group(1))


def adjust_volume(delta: int) -> int:
    """Move volume by `delta` percentage points and return the hardware readback."""

    current = get_volume()
    return set_volume(max(0, min(100, current + int(delta))))
