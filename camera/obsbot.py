"""Bounded OBSBOT Tiny SE pan/tilt control through standard V4L2 UVC ioctls."""

from __future__ import annotations

import errno
import fcntl
import os
import struct
from dataclasses import dataclass

DEFAULT_DEVICE = "/dev/video0"
UVC_UNITS_PER_DEGREE = 3600

_VIDIOC_QUERYCTRL = 0xC0445624
_VIDIOC_G_CTRL = 0xC008561B
_VIDIOC_S_CTRL = 0xC008561C
_CAMERA_CLASS_BASE = 0x009A0900
_PAN_ABSOLUTE = _CAMERA_CLASS_BASE + 8
_TILT_ABSOLUTE = _CAMERA_CLASS_BASE + 9

# Stay well away from the OBSBOT's physical stops even though the queried range
# is wider. These bounds are sufficient for the room-scanning demos.
SAFE_PAN_DEGREES = (-60.0, 60.0)
SAFE_TILT_DEGREES = (-30.0, 30.0)


class PTZError(RuntimeError):
    """Raised when the camera's UVC pan/tilt controls cannot be used."""


@dataclass(frozen=True)
class ControlInfo:
    control_id: int
    name: str
    minimum: int
    maximum: int
    step: int
    default: int
    flags: int


def _device() -> str:
    return os.environ.get("GEMMA_CAMERA_DEVICE", DEFAULT_DEVICE)


def _open_device() -> int:
    device = _device()
    try:
        return os.open(device, os.O_RDWR | os.O_NONBLOCK)
    except OSError as exc:
        raise PTZError(f"cannot open {device} for UVC control: {exc}") from exc


def _query_control(fd: int, control_id: int) -> ControlInfo:
    query = bytearray(
        struct.pack("=II32siiiiI2I", control_id, 0, bytes(32), 0, 0, 0, 0, 0, 0, 0)
    )
    try:
        fcntl.ioctl(fd, _VIDIOC_QUERYCTRL, query, True)
    except OSError as exc:
        if exc.errno == errno.EINVAL:
            raise PTZError(f"UVC control 0x{control_id:08x} is not exposed") from exc
        raise PTZError(f"failed to query UVC control 0x{control_id:08x}: {exc}") from exc
    _, _, raw_name, minimum, maximum, step, default, flags, _, _ = struct.unpack(
        "=II32siiiiI2I", query
    )
    name = raw_name.split(bytes([0]), 1)[0].decode(errors="replace")
    return ControlInfo(control_id, name, minimum, maximum, step, default, flags)


def _get_control(fd: int, control_id: int) -> int:
    value = bytearray(struct.pack("=Ii", control_id, 0))
    try:
        fcntl.ioctl(fd, _VIDIOC_G_CTRL, value, True)
    except OSError as exc:
        raise PTZError(f"failed to read UVC control 0x{control_id:08x}: {exc}") from exc
    _, current = struct.unpack("=Ii", value)
    return current


def _bounded_value(info: ControlInfo, requested: int) -> int:
    bounded = min(info.maximum, max(info.minimum, requested))
    step = max(1, info.step)
    return info.minimum + round((bounded - info.minimum) / step) * step


def _set_control(fd: int, info: ControlInfo, requested: int) -> int:
    target = _bounded_value(info, requested)
    value = bytearray(struct.pack("=Ii", info.control_id, target))
    try:
        fcntl.ioctl(fd, _VIDIOC_S_CTRL, value, True)
    except OSError as exc:
        raise PTZError(f"failed to set {info.name} to {target}: {exc}") from exc
    current = _get_control(fd, info.control_id)
    if abs(current - target) > max(1, info.step):
        raise PTZError(f"{info.name} readback {current} does not match target {target}")
    return current


def look_at(pan_deg: float, tilt_deg: float) -> tuple[float, float]:
    """Move to a safe absolute pan/tilt position and return the readback degrees."""

    safe_pan = min(SAFE_PAN_DEGREES[1], max(SAFE_PAN_DEGREES[0], float(pan_deg)))
    safe_tilt = min(SAFE_TILT_DEGREES[1], max(SAFE_TILT_DEGREES[0], float(tilt_deg)))
    fd = _open_device()
    try:
        pan_info = _query_control(fd, _PAN_ABSOLUTE)
        tilt_info = _query_control(fd, _TILT_ABSOLUTE)
        pan_value = _set_control(fd, pan_info, round(safe_pan * UVC_UNITS_PER_DEGREE))
        tilt_value = _set_control(fd, tilt_info, round(safe_tilt * UVC_UNITS_PER_DEGREE))
    finally:
        os.close(fd)
    return pan_value / UVC_UNITS_PER_DEGREE, tilt_value / UVC_UNITS_PER_DEGREE


def look_left() -> tuple[float, float]:
    return look_at(-45, 0)


def look_right() -> tuple[float, float]:
    return look_at(45, 0)


def look_up() -> tuple[float, float]:
    return look_at(0, -25)


def look_down() -> tuple[float, float]:
    return look_at(0, 25)


def look_center() -> tuple[float, float]:
    return look_at(0, 0)


def control_method() -> str:
    """Return the acceptance-report name for this implementation."""

    return "uvc"
