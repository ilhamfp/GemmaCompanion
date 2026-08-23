#!/usr/bin/env python3
"""Isolated native-audio probe; never run against the stage vision server."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.gemma import GemmaClient  # noqa: E402
from demos.companion import AGENT_DECISION_PROMPT, available_memory_bytes  # noqa: E402
from tools.registry import COMPANION_DECISION_SCHEMAS, tool_name  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("wav", type=Path)
    parser.add_argument("--expect-tool", required=True)
    parser.add_argument("--latency-limit", type=float, default=5.0)
    args = parser.parse_args()

    with urllib.request.urlopen("http://127.0.0.1:11434/slots", timeout=5) as response:
        slots = json.load(response)
    if len(slots) != 1:
        raise AssertionError(
            "native audio must be isolated on a freshly started GEMMA_PARALLEL=1 server; "
            f"found {len(slots)} slots"
        )

    client = GemmaClient()
    props = client.show()
    if not (props.get("modalities") or {}).get("audio"):
        raise AssertionError("loaded Gemma runtime does not advertise audio input")

    started = time.monotonic()
    text, calls = client.step(
        [
            {"role": "system", "content": f"{AGENT_DECISION_PROMPT}\nThe companion is awake."},
            {"role": "user", "content": "Treat the attached audio as the user's request."},
        ],
        tools=COMPANION_DECISION_SCHEMAS,
        audios=[args.wav],
        max_tokens=48,
        tool_choice="required",
    )
    latency = time.monotonic() - started
    selected = [tool_name(call) for call in calls]
    if args.expect_tool not in selected:
        raise AssertionError(
            f"expected {args.expect_tool!r}; selected={selected!r}; response={text!r}"
        )
    if latency >= args.latency_limit:
        raise AssertionError(f"native audio took {latency:.3f}s")
    available_mib = available_memory_bytes() / (1024 * 1024)
    print(
        f"direct_audio_tool: PASS; tool={args.expect_tool}; "
        f"latency_seconds={latency:.3f}; available_memory_mib={available_mib:.1f}"
    )
    print("result: PASS native Gemma audio selected a tool without Whisper")
    print("IMPORTANT: restart the normal two-slot llama.cpp server before any vision request")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
