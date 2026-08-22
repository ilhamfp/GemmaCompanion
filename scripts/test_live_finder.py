#!/usr/bin/env python3
"""Verify a visible AirPods case and a complete honest absent-object sweep."""

from __future__ import annotations

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
    positive = _search("Find my AirPods.", AIRPODS_TARGET)
    if not positive.found:
        raise AssertionError("live AirPods case was not found")
    if positive.direction != "center":
        raise AssertionError(f"front-tabletop AirPods direction was {positive.direction!r}")
    if not any(anchor in positive.location.casefold() for anchor in LOCATION_ANCHORS):
        raise AssertionError(f"AirPods location was not physically grounded: {positive.location!r}")

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
        f"direction={positive.direction}; location={positive.location}; "
        f"duration_seconds={positive.duration_seconds:.3f}"
    )
    print(
        "absent_negative: PASS; "
        f"target={ABSENT_TARGET}; duration_seconds={negative.duration_seconds:.3f}"
    )
    print(f"coverage_moves: {','.join(negative.gemma_moves)}")
    print(f"logs: positive={positive.log_path}; negative={negative.log_path}")
    print("result: PASS live AirPods detection and complete honest physical sweep")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
