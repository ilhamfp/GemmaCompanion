#!/usr/bin/env python3
"""Human-in-loop acceptance for AT-CSP1 mute-button barge-in."""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from audio.tts import synthesize  # noqa: E402
from camera.obsbot import look_center  # noqa: E402
from demos.companion import CompanionSession  # noqa: E402

LONG_LINE = (
    "I'm speaking now. Unmute the microphone, say look left clearly, and mute it again. "
    "You can interrupt me at any moment."
)


def main() -> int:
    look_center()
    session = CompanionSession(speech=True, microphone=True, log_dir=REPO_ROOT / "logs")
    with tempfile.TemporaryDirectory(prefix="gemma-physical-barge-") as directory:
        prompt_path = synthesize(LONG_LINE, directory)
        session.start(announce_scene=False)
        try:
            session.speaker.interrupt()
            print("READY: keep the mic muted until the long sentence starts.", flush=True)
            session.speaker.play_file(prompt_path)
            if not session.speaker.speaking.wait(timeout=5):
                raise TimeoutError("long playback did not start")
            print("NOW: unmute, say 'look left', then mute again.", flush=True)
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                result = session.last_result
                if result is not None and result.action == "look_left":
                    break
                if session.mic.last_error is not None:
                    raise RuntimeError(f"microphone failed: {session.mic.last_error}")
                if session.speaker.last_error is not None:
                    raise RuntimeError(f"speaker failed: {session.speaker.last_error}")
                if not session.speaker.speaking.is_set():
                    session.speaker.play_file(prompt_path)
                time.sleep(0.05)
            else:
                raise TimeoutError(
                    "no accepted look_left command within 90 seconds; "
                    f"max_rms={session.mic.max_rms:.0f}; "
                    f"start_rms={session.mic.segmenter.start_rms:.0f}; "
                    f"windows={session.mic.windows_read}"
                )

            assert session.last_result is not None
            if session.last_barge_in_at is None or session.last_segment_ended_at is None:
                raise AssertionError("barge-in timing evidence is incomplete")
            if session.barge_while_speaking_count < 1:
                raise AssertionError("no utterance began while playback was active")
            if session.last_result_at is None or session.last_barge_cancel_seconds is None:
                raise AssertionError("result timing evidence is incomplete")
            command_seconds = session.last_result_at - session.last_segment_ended_at
            if session.max_active_playback_cancel_seconds >= 0.3:
                raise AssertionError(
                    "playback cancellation took "
                    f"{session.max_active_playback_cancel_seconds:.3f}s"
                )
            if command_seconds >= 1.5:
                raise AssertionError(f"mute-to-look completion took {command_seconds:.3f}s")
            result = session.last_result
        finally:
            session.stop()

    print(
        f"barge_in: PASS; count={session.barge_in_count}; "
        f"while_speaking={session.barge_while_speaking_count}; "
        f"max_playback_cancel_seconds={session.max_active_playback_cancel_seconds:.4f}"
    )
    print(f"transcript: PASS; action={result.action}")
    print(f"command_after_segment_seconds: {command_seconds:.3f}; limit: <1.500")
    print(f"physical_direction: {result.direction}")
    print(f"session_log: {session.log_path}")
    print("result: PASS physical mute-button barge-in stopped speech and moved OBSBOT left")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
