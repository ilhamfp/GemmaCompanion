#!/usr/bin/env python3
"""Verify finder identity grounding against one previously captured frame."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from demos.elderly import ElderlyFinder  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--expect", choices=("found", "reject"), required=True)
    args = parser.parse_args()

    image = Path(args.image).expanduser().resolve()
    if not image.is_file():
        parser.error(f"image does not exist: {image}")

    finder = ElderlyFinder(speech=False)
    action, location = finder._inspect(str(image), "center", "look_left", args.target)
    if args.expect == "found" and action != "report_found":
        raise AssertionError(f"expected a grounded find, got action={action!r}")
    if args.expect == "reject" and action == "report_found":
        raise AssertionError(f"weak candidate was accepted at {location!r}")

    print(
        f"finder_evidence: PASS; expected={args.expect}; action={action}; "
        f"location={location or 'none'}; log={finder.loop.log_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
