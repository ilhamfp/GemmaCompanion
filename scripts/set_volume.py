#!/usr/bin/env python3
"""Show or set the AT-CSP1 playback volume."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from audio.volume import DEFAULT_PLAYBACK_VOLUME, get_volume, set_volume  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="AT-CSP1 hardware playback volume")
    parser.add_argument(
        "percent",
        nargs="?",
        type=int,
        help=f"volume from 0 to 100 (boot default: {DEFAULT_PLAYBACK_VOLUME})",
    )
    args = parser.parse_args()

    volume = get_volume() if args.percent is None else set_volume(args.percent)
    print(f"playback_volume_percent: {volume}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
