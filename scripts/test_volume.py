#!/usr/bin/env python3
"""Verify AT-CSP1 hardware playback volume control and leave it at 85%."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from audio.volume import adjust_volume, get_volume, set_volume  # noqa: E402


def main() -> int:
    initial = get_volume()
    lower = set_volume(75)
    final = adjust_volume(10)
    if abs(lower - 75) > 1:
        raise AssertionError(f"75% request read back as {lower}%")
    if abs(final - 85) > 1:
        raise AssertionError(f"+10 adjustment read back as {final}%")
    print(f"initial_volume_percent: {initial}")
    print(f"set_volume: PASS; requested=75; readback={lower}")
    print(f"adjust_volume: PASS; delta=+10; readback={final}")
    print("result: PASS AT-CSP1 playback volume is adjustable; boot default left at 85%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
