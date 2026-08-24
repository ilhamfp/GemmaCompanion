#!/usr/bin/env python3
"""Verify resident Whisper accuracy, latency, and memory headroom."""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from audio.fast_stt import transcribe_fast  # noqa: E402


def _available_mib() -> float:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1024
    raise RuntimeError("MemAvailable is unavailable")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wav")
    parser.add_argument("--expect", required=True)
    parser.add_argument("--limit", type=float, default=1.5)
    args = parser.parse_args()

    started = time.monotonic()
    transcript = transcribe_fast(args.wav, fallback_to_cli=False)
    latency = time.monotonic() - started
    expected_words = set(re.findall(r"[a-z]+", args.expect.casefold()))
    actual_words = set(re.findall(r"[a-z]+", transcript.casefold()))
    if not expected_words <= actual_words:
        raise AssertionError(f"expected words {sorted(expected_words)}, transcript={transcript!r}")
    if latency >= args.limit:
        raise AssertionError(f"resident STT took {latency:.3f}s, limit is {args.limit:.3f}s")
    available = _available_mib()
    if available < 500:
        raise AssertionError(f"only {available:.1f} MiB available")

    print(
        "server: whisper.cpp 1.9.3; model: tiny.en Q5_1; threads: 6; "
        "audio_context: 1280; device: CPU"
    )
    print(f"transcript: {transcript}")
    print(f"latency_seconds: {latency:.3f}; limit: <{args.limit:.3f}")
    print(f"available_memory_mib: {available:.1f}; limit: >500")
    print("result: PASS resident offline STT meets accuracy, latency, and memory limits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
