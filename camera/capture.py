"""Still-image capture for the OBSBOT Tiny SE."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from PIL import Image


DEFAULT_DEVICE = "/dev/video0"
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 720
DEFAULT_MAX_LONG_EDGE = 1024


class CameraCaptureError(RuntimeError):
    """Raised when the camera cannot produce a usable JPEG."""


def capture_image(
    output_dir: str | os.PathLike[str] | None = None,
    *,
    device: str | None = None,
    max_long_edge: int | None = None,
    warmup_frames: int = 4,
) -> str:
    """Capture a fresh JPEG and return its absolute path.

    The OBSBOT provides MJPEG in hardware. GStreamer grabs a short burst so stale
    auto-exposure frames are discarded, and Pillow normalizes the last frame to
    RGB while bounding its long edge for the vision model.
    """

    camera_device = device or os.environ.get("GEMMA_CAMERA_DEVICE", DEFAULT_DEVICE)
    if max_long_edge is None:
        max_long_edge = int(
            os.environ.get("GEMMA_CAMERA_MAX_LONG_EDGE", str(DEFAULT_MAX_LONG_EDGE))
        )
    if not Path(camera_device).exists():
        raise CameraCaptureError(f"camera device does not exist: {camera_device}")
    if max_long_edge < 64:
        raise ValueError("max_long_edge must be at least 64 pixels")
    if warmup_frames < 1:
        raise ValueError("warmup_frames must be at least 1")
    if shutil.which("gst-launch-1.0") is None:
        raise CameraCaptureError("gst-launch-1.0 is not installed")

    destination = Path(output_dir or Path.cwd() / "captures").expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    final_path = destination / f"capture-{uuid.uuid4().hex}.jpg"

    with tempfile.TemporaryDirectory(prefix="gemma-camera-") as temp_dir:
        frame_pattern = str(Path(temp_dir) / "frame-%02d.jpg")
        command = [
            "gst-launch-1.0",
            "-q",
            "v4l2src",
            f"device={camera_device}",
            f"num-buffers={warmup_frames}",
            "!",
            f"image/jpeg,width={DEFAULT_WIDTH},height={DEFAULT_HEIGHT},framerate=30/1",
            "!",
            "jpegparse",
            "!",
            "multifilesink",
            f"location={frame_pattern}",
        ]
        started = time.monotonic()
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except subprocess.TimeoutExpired as exc:
            raise CameraCaptureError("camera capture timed out after 5 seconds") from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown GStreamer error"
            raise CameraCaptureError(f"GStreamer capture failed: {detail}")

        frames = sorted(Path(temp_dir).glob("frame-*.jpg"))
        if not frames:
            raise CameraCaptureError("camera returned no JPEG frames")
        source_frame = frames[-1]

        try:
            with Image.open(source_frame) as image:
                image.load()
                image = image.convert("RGB")
                if max(image.size) > max_long_edge:
                    image.thumbnail((max_long_edge, max_long_edge), Image.Resampling.LANCZOS)
                image.save(final_path, format="JPEG", quality=90, optimize=True)
        except OSError as exc:
            raise CameraCaptureError(f"captured frame is not a valid image: {exc}") from exc

        if time.monotonic() - started > 5:
            raise CameraCaptureError("camera capture exceeded internal five-second limit")

    return str(final_path)
