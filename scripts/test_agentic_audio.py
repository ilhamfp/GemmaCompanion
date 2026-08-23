#!/usr/bin/env python3
"""Verify semantic tool selection and dependent embodied tool chaining."""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.gemma import GemmaClient  # noqa: E402
from demos.companion import (  # noqa: E402
    AGENT_DECISION_PROMPT,
    CompanionSession,
    available_memory_bytes,
)
from tools.registry import COMPANION_DECISION_SCHEMAS, tool_name  # noqa: E402

TEXT_CASES = (
    ("Aim your gaze toward the port side.", {"look_left"}),
    ("Sweep your attention toward starboard.", {"look_right"}),
    ("Tilt the lens toward the ceiling.", {"look_up"}),
    ("Angle the lens toward the floor.", {"look_down"}),
    ("Return your gaze to its neutral forward pose.", {"look_center"}),
    ("Give me a visual rundown of whatever is presently before you.", {"inspect_view"}),
    ("Please decipher the writing on the card I am presenting to the lens.", {"inspect_view"}),
    ("Track down the spectacles I misplaced.", {"find_object"}),
    ("Could you make your voice a touch softer?", {"make_voice_softer"}),
    ("Raise your speaking loudness by one notch.", {"make_voice_louder"}),
    ("Set the speaker loudness at seventy-three percent.", {"set_volume"}),
    ("Please enter an idle state for now.", {"sleep"}),
    ("Cut off the current response.", {"cancel_current_response"}),
)


def selected_tools(
    client: GemmaClient,
    *,
    text: str,
    audio: Path | None = None,
    state: str = "The companion is awake.",
) -> tuple[set[str], str, float]:
    started = time.monotonic()
    response, calls = client.step(
        [
            {"role": "system", "content": f"{AGENT_DECISION_PROMPT}\n{state}"},
            {"role": "user", "content": text},
        ],
        tools=COMPANION_DECISION_SCHEMAS,
        audios=[audio] if audio else None,
        max_tokens=24,
        tool_choice="required",
    )
    latency = time.monotonic() - started
    return {tool_name(call) for call in calls}, response, latency


def main() -> int:
    client = GemmaClient()
    client.show()

    for prompt, expected in TEXT_CASES:
        actual, response, latency = selected_tools(client, text=prompt)
        if not expected <= actual:
            raise AssertionError(
                f"semantic tool mismatch: prompt={prompt!r}; expected={sorted(expected)}; "
                f"actual={sorted(actual)}; response={response!r}"
            )
        if latency >= 5.0:
            raise AssertionError(f"semantic tool selection took {latency:.3f}s: {prompt!r}")
        print(
            f"text_tool: PASS; prompt={prompt}; tools={','.join(sorted(actual))}; "
            f"latency_seconds={latency:.3f}"
        )

    ordinary_tools, ordinary_response, ordinary_latency = selected_tools(
        client,
        text="Why do healthy leaves usually appear green?",
    )
    if ordinary_tools not in (set(), {"respond_normally"}) or (
        not ordinary_tools and not ordinary_response
    ):
        raise AssertionError(
            f"ordinary knowledge was not ordinary chat: tools={ordinary_tools}; "
            f"response={ordinary_response!r}"
        )
    print(
        f"ordinary_gate: PASS; tools={','.join(sorted(ordinary_tools)) or 'direct_text'}; "
        f"latency_seconds={ordinary_latency:.3f}"
    )

    session = CompanionSession(speech=False, microphone=False, gemma=client)
    try:
        chained = session.handle_text(
            "Turn toward the port side and report the scene from there."
        )
        if chained.action != "look_left_and_inspect" or not chained.image_path:
            raise AssertionError(f"dependent movement/vision tools did not chain: {chained}")
        if not Path(chained.image_path).is_file():
            raise AssertionError(f"chained fresh frame is missing: {chained.image_path}")
        print(
            f"dependent_tools: PASS; action={chained.action}; frame={chained.image_path}; "
            f"latency_seconds={chained.latency_seconds:.3f}"
        )
    finally:
        session.stop()

    available_mib = available_memory_bytes() / (1024 * 1024)
    if available_mib < 500:
        raise AssertionError(f"only {available_mib:.1f} MiB remains")
    print(f"available_memory_mib: {available_mib:.1f}; limit: >500")
    print("result: PASS Gemma semantically selects and chains embodied tools")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
