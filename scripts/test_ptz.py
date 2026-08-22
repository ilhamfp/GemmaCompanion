#!/usr/bin/env python3
"""M2 acceptance test for physical OBSBOT pan/tilt movement."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from camera.capture import capture_image  # noqa: E402
from camera.obsbot import control_method, look_center, look_left, look_right  # noqa: E402


def _comparison_pixels(path: str) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB").resize((256, 144)), dtype=np.float32)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settle", type=float, default=1.0)
    parser.add_argument("--threshold", type=float, default=8.0)
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "captures" / "ptz"))
    args = parser.parse_args()

    if args.settle < 0.5:
        raise ValueError("settle delay must be at least 0.5 seconds")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Start from a deterministic home position, then perform the exact acceptance
    # sequence. A final readback at center proves the camera returned home.
    look_center()
    time.sleep(args.settle)

    left_position = look_left()
    time.sleep(args.settle)
    left_path = capture_image(output_dir)

    right_position = look_right()
    time.sleep(args.settle)
    right_path = capture_image(output_dir)

    center_position = look_center()
    time.sleep(args.settle)

    left = _comparison_pixels(left_path)
    right = _comparison_pixels(right_path)
    mean_pixel_diff = float(np.mean(np.abs(left - right)))

    assert left_position[0] < -30, f"left readback was not left: {left_position}"
    assert right_position[0] > 30, f"right readback was not right: {right_position}"
    assert abs(center_position[0]) <= 1 and abs(center_position[1]) <= 1, (
        f"center readback was not home: {center_position}"
    )
    assert mean_pixel_diff > args.threshold, (
        f"left/right mean pixel diff {mean_pixel_diff:.3f} did not exceed {args.threshold:.3f}"
    )

    print(f"method: {control_method()}")
    print("sequence: look_left,capture,look_right,capture,look_center")
    print(f"frames: left={left_path}; right={right_path}")
    print(f"mean_pixel_diff: {mean_pixel_diff:.3f}; threshold: {args.threshold:.3f}")
    print("result: PASS physical PTZ frames differ and camera returned center")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
