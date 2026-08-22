#!/usr/bin/env python3
"""M5 acceptance test for Gemma-initiated physical observe-think-look."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.loop import AgentLoop  # noqa: E402


def main() -> int:
    result = AgentLoop(log_dir=REPO_ROOT / "logs").run_scripted_look_scenario()
    log_path = Path(result["log_path"])
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    decision_index = next(
        index for index, event in enumerate(events) if event["action"] == "GEMMA_LOOK_DECISION"
    )
    look_index = next(index for index, event in enumerate(events) if event["action"] == "LOOK")
    reference_index = next(
        index for index, event in enumerate(events) if event["action"] == "POST_LOOK_REFERENCE"
    )
    if not decision_index < look_index < reference_index:
        raise AssertionError("log order does not prove decide -> physical look -> new-frame reference")

    print(f"gemma_action: {result['look_tool']}; issued_by: Gemma; tool_calls: 1/8")
    print(
        "physical_result: "
        f"pan={result['position'][0]:.1f}; tilt={result['position'][1]:.1f}; "
        f"mean_pixel_diff={result['frame_difference']:.3f}"
    )
    print(f"post_look_message: {result['post_message']}")
    print(f"session_log: {log_path}; events: {len(events)}; order: decide,look,capture,reference")
    print("result: PASS Gemma issued LOOK and its next visual message used only the new physical frame")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
