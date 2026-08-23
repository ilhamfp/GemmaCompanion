#!/usr/bin/env python3
"""Verify arbitrary visible-reference wording captures and uses a fresh frame."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.gemma import GemmaClient  # noqa: E402
from demos.companion import AGENT_DECISION_PROMPT, CompanionSession  # noqa: E402
from tools.registry import COMPANION_DECISION_SCHEMAS, tool_name  # noqa: E402

VISUAL_PROMPTS = (
    "What color is the object I'm holding?",
    "Can you identify this object?",
    "What is written on this label?",
)


def _selected_tool(client: GemmaClient, prompt: str) -> tuple[str, str]:
    text, calls = client.step(
        [
            {"role": "system", "content": AGENT_DECISION_PROMPT},
            {"role": "user", "content": prompt},
        ],
        tools=COMPANION_DECISION_SCHEMAS,
        tool_choice="required",
    )
    return (tool_name(calls[0]) if calls else "none"), text


def main() -> int:
    subprocess.run([str(REPO_ROOT / "scripts" / "ensure_gemma.sh")], check=True)
    client = GemmaClient()
    model_selections = [_selected_tool(client, prompt)[0] for prompt in VISUAL_PROMPTS]

    general_tool, general_text = _selected_tool(client, "Why is the sky blue?")
    if general_tool not in {"none", "respond_normally"} or (
        general_tool == "none" and not general_text
    ):
        raise AssertionError("ordinary knowledge question did not select normal response")
    finder_tool, _ = _selected_tool(client, "Find my blue mug.")
    if finder_tool != "find_object":
        raise AssertionError(f"finder control selected {finder_tool!r}")

    session = CompanionSession(speech=False, microphone=False, log_dir=REPO_ROOT / "logs")
    results = [session.handle_text(prompt) for prompt in VISUAL_PROMPTS]
    frame_paths = [result.image_path for result in results]
    if any(result.action != "visual_question" for result in results):
        raise AssertionError(f"visual requests did not all inspect: {[r.action for r in results]!r}")
    if any(not path or not Path(path).is_file() for path in frame_paths):
        raise AssertionError(f"one or more fresh frames are missing: {frame_paths!r}")
    if len(set(frame_paths)) != len(frame_paths):
        raise AssertionError("visual requests reused a prior frame")

    for index, (prompt, result) in enumerate(zip(VISUAL_PROMPTS, results), start=1):
        print(
            f"visual_route_{index}: PASS; prompt={prompt}; action={result.action}; "
            f"router={model_selections[index - 1]}; latency_seconds={result.latency_seconds:.3f}; "
            f"frame={result.image_path}"
        )
    print(
        "negative_controls: PASS; general knowledge stayed chat; "
        "misplaced object stayed find_object"
    )
    print(f"fresh_frames: PASS; unique={len(set(frame_paths))}/{len(frame_paths)}")
    print("result: PASS arbitrary visible-reference wording captured fresh camera frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
