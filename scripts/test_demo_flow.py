#!/usr/bin/env python3
"""Verify the boot, directional vision, and generic finder-tool demo beats."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from demos.companion import READY_CUE, CompanionSession  # noqa: E402
from tools.registry import COMPANION_DECISION_SCHEMAS, tool_name  # noqa: E402


def main() -> int:
    subprocess.run([str(REPO_ROOT / "scripts" / "ensure_gemma.sh")], check=True)
    session = CompanionSession(speech=False, microphone=False, log_dir=REPO_ROOT / "logs")
    session.start(announce_scene=True)
    try:
        deadline = time.monotonic() + 30
        while session.last_result is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if session.last_result is None or session.last_result.response != READY_CUE:
            raise AssertionError("boot greeting was not grounded and ready")

        left = session.handle_text("Orient toward the port side.")
        left_view = session.handle_text("Summarize the scene now facing the lens.")
        right = session.handle_text("Orient toward the starboard side.")
        right_view = session.handle_text("Report the current scene from this new angle.")
        if left.action != "look_left" or right.action != "look_right":
            raise AssertionError("directional demo commands did not move physically")
        if not left_view.image_path or not right_view.image_path:
            raise AssertionError("directional descriptions did not use fresh frames")

        _, calls = session.gemma.step(
            [
                {
                    "role": "system",
                    "content": (
                        "When the user asks you to find a misplaced object, call find_object "
                        "with a concise visual target."
                    ),
                },
                {"role": "user", "content": "Please find my AirPods."},
            ],
            tools=COMPANION_DECISION_SCHEMAS,
            tool_choice="required",
        )
        if not calls or tool_name(calls[0]) != "find_object":
            raise AssertionError(f"Gemma did not select find_object: {calls}")
        arguments = (calls[0].get("function") or {}).get("arguments") or {}
        target = " ".join(str(arguments.get("target") or "").split())
        if "airpod" not in target.casefold():
            raise AssertionError(f"Gemma extracted an unexpected finder target: {target!r}")

        scam = session.handle_text(
            "Assess whether the message I am presenting to the lens is fraudulent."
        )
        if scam.action != "visual_question" or not scam.image_path:
            raise AssertionError(f"scam question did not request fresh vision: {scam}")
    finally:
        session.stop()

    print(f"boot_greeting: PASS; cue={READY_CUE}")
    print(
        "directional_vision: PASS; sequence=left,describe,right,describe; "
        f"left_response={left_view.response}; right_response={right_view.response}"
    )
    print(f"finder_tool: PASS; issued_by=Gemma; target={target}")
    print("scam_route: PASS; fresh_camera_visual_question=yes")
    print("result: PASS boot-to-interaction demo routing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
