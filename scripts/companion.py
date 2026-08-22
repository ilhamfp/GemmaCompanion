#!/usr/bin/env python3
"""Launch the persistent Gemma Companion session."""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from demos.companion import CompanionSession  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Continuous offline Gemma Companion")
    parser.add_argument("--text", action="store_true", help="use a terminal loop instead of the microphone")
    parser.add_argument("--no-speech", action="store_true", help="print responses without playback")
    parser.add_argument(
        "--no-scene-announcement",
        action="store_true",
        help="announce generic readiness instead of describing a fresh boot frame",
    )
    parser.add_argument("--command", help="execute one text command and exit")
    args = parser.parse_args()

    session = CompanionSession(
        speech=not args.no_speech,
        microphone=not args.text and args.command is None,
        log_dir=REPO_ROOT / "logs",
    )
    announce_scene = not args.no_scene_announcement

    if not args.text and args.command is None:
        print("Companion starting. Keep the AT-CSP1 muted until you want to speak.", flush=True)
        signal.signal(signal.SIGTERM, lambda _signum, _frame: session.request_stop())
        signal.signal(signal.SIGHUP, lambda _signum, _frame: session.request_stop())
        try:
            session.run_forever(announce_scene=announce_scene)
        except KeyboardInterrupt:
            print("Companion stopped.", flush=True)
        return 0

    session.start(announce_scene=announce_scene)
    try:
        if args.command:
            result = session.handle_text(args.command)
            print(
                f"action: {result.action}; direction: {result.direction}; "
                f"latency_seconds: {result.latency_seconds:.3f}"
            )
            return 0
        print("Text companion ready. Type a command, or 'exit' to stop.", flush=True)
        while True:
            text = input("You> ").strip()
            if text.casefold() in {"exit", "quit"}:
                return 0
            if text:
                session.handle_text(text)
    finally:
        session.stop()


if __name__ == "__main__":
    raise SystemExit(main())
