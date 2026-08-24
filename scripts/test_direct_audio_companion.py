#!/usr/bin/env python3
"""Verify native Gemma audio through a complete embodied companion action."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from demos.companion import CompanionSession, available_memory_bytes  # noqa: E402


class NullSpeaker:
    """Avoid loading a second TTS engine while probing Gemma memory."""

    def __init__(self) -> None:
        self.speaking = threading.Event()

    def interrupt(self) -> float:
        return 0.0

    def say(self, *_args, **_kwargs) -> None:
        return None

    def wait(self, *_args, **_kwargs) -> bool:
        return True

    def close(self, *_args, **_kwargs) -> None:
        return None


def server_json(route: str) -> object:
    with urllib.request.urlopen(f"http://127.0.0.1:11434{route}", timeout=5) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wav", type=Path)
    parser.add_argument(
        "--expect-action",
        action="append",
        required=True,
        help="accepted CompanionResult action; repeat for multiple accepted outcomes",
    )
    parser.add_argument("--latency-limit", type=float, default=220.0)
    args = parser.parse_args()

    # These are the crash-safe direct profile defaults from run_companion.sh.
    # The verifier is commonly launched over SSH rather than as a service child,
    # so it must not silently fall back to the production 30-second GPU timeout.
    os.environ.setdefault("GEMMA_REQUEST_TIMEOUT_SECONDS", "120")
    os.environ.setdefault("GEMMA_CAMERA_MAX_LONG_EDGE", "512")
    os.environ.setdefault("GEMMA_EDGE_DETAIL_MAX_LONG_EDGE", "512")

    wav = args.wav.expanduser().resolve()
    if not wav.is_file():
        raise FileNotFoundError(wav)
    props = server_json("/props")
    if not (props.get("modalities") or {}).get("audio"):
        raise AssertionError("loaded Gemma runtime does not advertise native audio")
    slots = server_json("/slots")
    memory_before = available_memory_bytes() / (1024 * 1024)
    print(f"direct_audio_profile: slots={len(slots)}; memory_before_mib={memory_before:.1f}")

    session = CompanionSession(
        speech=False,
        microphone=False,
        speech_mode="direct",
        speaker=NullSpeaker(),
    )
    started = time.monotonic()
    try:
        result = session.handle_audio(str(wav))
    finally:
        session.stop()
    elapsed = time.monotonic() - started
    if result.action not in set(args.expect_action):
        raise AssertionError(
            f"expected one of {args.expect_action!r}; action={result.action!r}; "
            f"response={result.response!r}"
        )
    if elapsed >= args.latency_limit:
        raise AssertionError(f"native-audio embodied turn took {elapsed:.3f}s")
    with urllib.request.urlopen("http://127.0.0.1:11434/health", timeout=5) as response:
        if response.status != 200:
            raise AssertionError(f"Gemma health returned {response.status}")
    memory_after = available_memory_bytes() / (1024 * 1024)
    print(
        "direct_audio_embodied: PASS; "
        f"action={result.action}; direction={result.direction}; "
        f"latency_seconds={result.latency_seconds:.3f}; response={result.response}"
    )
    print(
        f"direct_audio_health: PASS; memory_after_mib={memory_after:.1f}; "
        "gemma_http=200"
    )
    print("result: PASS Gemma consumed audio and completed an embodied action without Whisper")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
