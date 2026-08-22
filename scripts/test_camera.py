#!/usr/bin/env python3
"""M1 acceptance test: capture a fresh, bounded OBSBOT JPEG in under 2 seconds."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from PIL import Image, ImageStat

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from camera.capture import DEFAULT_DEVICE, capture_image  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "captures"))
    parser.add_argument("--device", default=os.environ.get("GEMMA_CAMERA_DEVICE", DEFAULT_DEVICE))
    args = parser.parse_args()

    started = time.monotonic()
    path = Path(capture_image(args.output_dir, device=args.device))
    elapsed = time.monotonic() - started

    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        width, height = image.size
        grayscale = image.convert("L")
        contrast = ImageStat.Stat(grayscale).stddev[0]

    assert path.is_file() and path.stat().st_size > 10_000, "captured JPEG is unexpectedly small"
    assert max(width, height) <= 1024, "captured JPEG exceeds the model input bound"
    assert contrast > 2.0, "captured JPEG appears blank"
    assert elapsed < 2.0, f"capture took {elapsed:.3f}s; acceptance limit is 2.000s"

    print(f"device: {args.device}")
    print(f"capture_path: {path}")
    print(f"dimensions: {width}x{height}; bytes: {path.stat().st_size}; contrast_stddev: {contrast:.2f}")
    print(f"elapsed_seconds: {elapsed:.3f}")
    print("result: PASS fresh JPEG captured in under 2 seconds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
