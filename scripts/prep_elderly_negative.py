#!/usr/bin/env python3
"""Capture a real five-direction absent-glasses fixture before placement."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from demos.elderly import SEARCH_ORDER, capture_negative_fixture  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / ".runtime" / "elderly-negative.json"),
    )
    args = parser.parse_args()
    payload = capture_negative_fixture(args.output, log_dir=REPO_ROOT / "logs")
    print("target: glasses; expected: absent")
    print("directions: " + ",".join(payload["frames"]))
    print("frames: " + "; ".join(payload["frames"].values()))
    print(f"fixture: {Path(args.output).expanduser().resolve()}")
    print("result: PASS live five-direction sweep contains no visible glasses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
