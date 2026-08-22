#!/usr/bin/env python3
"""Verify a visible AirPods case and a complete honest absent-object sweep."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from camera.obsbot import look_center  # noqa: E402
from demos.elderly import ElderlyFinder, SEARCH_ORDER  # noqa: E402

AIRPODS_TARGET = "small white Apple AirPods wireless-earbud charging case"
ABSENT_TARGET = "bright magenta stapler"
LOCATION_ANCHORS = ("table", "desk", "laptop", "phone", "smartphone")


def _search(request: str, target: str):
    try:
        return ElderlyFinder(speech=False).search_live(request, target=target)
    finally:
        look_center()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-direction", choices=SEARCH_ORDER)
    parser.add_argument("--positive-only", action="store_true")
    parser.add_argument("--repeat-positive", type=int, default=1)
    args = parser.parse_args()
    if args.repeat_positive < 1:
        parser.error("--repeat-positive must be at least 1")

    positives = []
    for run in range(1, args.repeat_positive + 1):
        positive = _search("Find my AirPods.", AIRPODS_TARGET)
        if not positive.found:
            raise AssertionError(f"live AirPods case was not found on run {run}")
        if positive.direction not in SEARCH_ORDER:
            raise AssertionError(f"AirPods direction was invalid: {positive.direction!r}")
        if args.expected_direction and positive.direction != args.expected_direction:
            raise AssertionError(
                f"AirPods direction was {positive.direction!r}, expected {args.expected_direction!r}"
            )
        if not any(anchor in positive.location.casefold() for anchor in LOCATION_ANCHORS):
            raise AssertionError(
                f"AirPods location was not physically grounded: {positive.location!r}"
            )
        positives.append(positive)
        print(
            f"airpods_positive_{run}: PASS; direction={positive.direction}; "
            f"location={positive.location}; duration_seconds={positive.duration_seconds:.3f}; "
            f"log={positive.log_path}"
        )

    if args.positive_only:
        print(f"result: PASS live AirPods detection repeated {len(positives)}/{len(positives)}")
        return 0

    negative = _search(f"Find the {ABSENT_TARGET}.", ABSENT_TARGET)
    expected_moves = tuple(f"look_{direction}" for direction in SEARCH_ORDER[1:])
    if negative.found:
        raise AssertionError("finder hallucinated the deliberately absent target")
    if negative.gemma_moves != expected_moves:
        raise AssertionError(
            f"incomplete sweep {negative.gemma_moves!r}; expected {expected_moves!r}"
        )

    print(
        "airpods_positive: PASS; "
        f"direction={positives[-1].direction}; location={positives[-1].location}; "
        f"duration_seconds={positives[-1].duration_seconds:.3f}"
    )
    print(
        "absent_negative: PASS; "
        f"target={ABSENT_TARGET}; duration_seconds={negative.duration_seconds:.3f}"
    )
    print(f"coverage_moves: {','.join(negative.gemma_moves)}")
    print(f"logs: positive={positives[-1].log_path}; negative={negative.log_path}")
    print("result: PASS live AirPods detection and complete honest physical sweep")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
