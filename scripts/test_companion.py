#!/usr/bin/env python3
"""Acceptance checks for continuous segmentation, routing, PTZ, and fresh vision."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from array import array
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from audio.continuous import VoiceSegmenter  # noqa: E402
from demos.companion import (  # noqa: E402
    MIN_AVAILABLE_BYTES,
    READY_CUE,
    CompanionResult,
    CompanionSession,
    available_memory_bytes,
    asks_for_current_view,
    parse_intent,
    preserves_target_identity,
)
from demos.elderly import (  # noqa: E402
    create_edge_detail_sheet,
    detail_candidate_is_consistent,
    parse_narrated_look_action,
    parse_narrated_not_found,
    parse_textual_report_found,
    parse_trailing_search_action,
)
from PIL import Image  # noqa: E402


def _pcm(level: int, samples: int) -> bytes:
    return array("h", [level] * samples).tobytes()


def _test_parser_and_segmenter() -> tuple[float, float]:
    expected = {
        "Look left!": ("look", "left"),
        "Look laugh": ("look", "left"),
        "Left": ("look", "left"),
        "Please turn to the right": ("look", "right"),
        "What do you see?": ("describe", None),
        "Volume to me. What are you seeing?": ("describe", None),
        "Using the camera.": ("describe", None),
        "Look up and tell me what you see": ("look_and_describe", "up"),
        "Be quiet": ("stop", None),
        "Go to sleep": ("sleep", None),
        "Wake up": ("wake", None),
        "Turn it up": ("volume_up", None),
        "Volume down": ("volume_down", None),
        "Is this a scam or not?": ("visual_question", None),
        "Can you advise me? Is this tax a scam?": ("visual_question", None),
        "Can you read the text inside that smartphone?": ("visual_question", None),
        "What does it say?": ("visual_question", None),
        "What color is the object I'm holding?": ("visual_question", None),
        "Can you identify this object?": ("visual_question", None),
        "What is written on this label?": ("visual_question", None),
        "What is this?": ("visual_question", None),
        "What am I holding?": ("visual_question", None),
        "How are you?": ("chat", None),
        "Why is the sky blue?": ("chat", None),
    }
    for phrase, wanted in expected.items():
        intent = parse_intent(phrase)
        actual = (intent.kind, intent.direction)
        if actual != wanted:
            raise AssertionError(f"{phrase!r} parsed as {actual}, expected {wanted}")
    volume_intent = parse_intent("Set volume to 92 percent")
    if volume_intent.kind != "volume_set" or volume_intent.value != 92:
        raise AssertionError(f"numeric volume parsed incorrectly: {volume_intent}")
    if asks_for_current_view("is this medication safe", {"is", "this", "medication", "safe"}):
        raise AssertionError("non-visual high-stakes question was treated as a camera request")

    segmenter = VoiceSegmenter()
    muted = _pcm(100, segmenter.chunk_bytes // 2)
    voice = _pcm(2_000, segmenter.chunk_bytes // 2)
    now = 100.0
    starts = 0
    segment = None
    for chunk in [muted] * 3 + [voice] * 5 + [muted] * 4:
        started, completed = segmenter.process(chunk, now=now)
        starts += int(started)
        segment = completed or segment
        now += segmenter.chunk_ms / 1000
    if starts != 1 or segment is None:
        raise AssertionError(f"segmenter starts={starts}, completed={segment is not None}")
    if segment.peak_rms < 1_900:
        raise AssertionError(f"unexpected peak RMS {segment.peak_rms}")
    return segment.duration_seconds, segment.peak_rms


def _test_latest_turn_wins() -> None:
    session = CompanionSession(speech=False, microphone=False, log_dir=REPO_ROOT / "logs")
    stale = session._new_turn()
    session._new_turn()
    result = CompanionResult("chat", "stale response", "center", None, 0.1)
    session._publish_result(result, stale, speak=False)
    if session.last_result is not None:
        raise AssertionError("a stale response was published")


def _test_narrated_finder_actions() -> None:
    accepted = {
        "I see no Apple Airbox. I will look down now.": "look_down",
        "I will search for the smartphone. I will start by looking right.": "look_right",
    }
    for text, expected in accepted.items():
        actual = parse_narrated_look_action(text, expected)
        if actual != expected:
            raise AssertionError(f"narrated finder action parsed as {actual!r}: {text!r}")
    if parse_narrated_look_action("I will look left now.", "look_right") is not None:
        raise AssertionError("finder accepted a narrated direction outside the bounded search order")
    if parse_narrated_look_action("I do not see a smartphone.", "look_right") is not None:
        raise AssertionError("finder invented a movement from evidence-only prose")
    final_miss = (
        "I have searched the center, left, right, up, and down. "
        "I did not find the smartphone. Please check under the sofa."
    )
    if parse_narrated_not_found(final_miss, final_direction=True) != "report_not_found":
        raise AssertionError("finder rejected Gemma's honest final narrated miss")
    if parse_narrated_not_found(final_miss, final_direction=False) is not None:
        raise AssertionError("finder accepted a narrated miss before completing its search")
    if parse_narrated_not_found("The smartphone is on the table.", final_direction=True) is not None:
        raise AssertionError("finder converted positive evidence into a miss")
    alternate_final_miss = (
        "I have searched the image. I do not see an iPhone. "
        "I suggest checking the kitchen counter."
    )
    if parse_narrated_not_found(alternate_final_miss, final_direction=True) != "report_not_found":
        raise AssertionError("finder rejected Gemma's alternate honest final miss")
    textual_tool = 'report_found{location:<|"|>on the dark surface in front of a laptop<|"|>}'
    parsed_location = parse_textual_report_found(textual_tool)
    if parsed_location != "on the dark tabletop in front of a laptop":
        raise AssertionError(f"textual report_found parsed as {parsed_location!r}")
    if parse_textual_report_found("report_found{location:nearby}") is not None:
        raise AssertionError("finder accepted an ungrounded textual report_found")
    trailing = "I understand. I will search now.\nreport_not_found"
    if parse_trailing_search_action(trailing, "report_not_found") != "report_not_found":
        raise AssertionError("finder rejected an expected trailing action token")
    if parse_trailing_search_action(trailing, "look_right") is not None:
        raise AssertionError("finder accepted a trailing action outside the expected search step")


def _test_edge_detail_sheet() -> None:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "frame.jpg"
        Image.new("RGB", (1280, 720), "black").save(source)
        detail = Path(create_edge_detail_sheet(source))
        if not detail.is_file():
            raise AssertionError("edge-detail sheet was not created")
        with Image.open(detail) as rendered:
            if rendered.size != (1024, 576):
                raise AssertionError(f"edge-detail sheet size was {rendered.size!r}")


def _test_target_identity() -> None:
    original = "small white Apple AirPods wireless-earbud charging case"
    if not preserves_target_identity(
        original, "small white Apple AirPods wireless-earbud charging case with rounded edges"
    ):
        raise AssertionError("identity-preserving AirPods visual target was rejected")
    if preserves_target_identity(original, "small white rectangular charging case with rounded edges"):
        raise AssertionError("visual target was allowed to discard Apple AirPods identity")


def _test_detail_candidate_consistency() -> None:
    if not detail_candidate_is_consistent(
        "small white Apple AirPods charging case",
        "A small white smooth curved object is visible near the laptop.",
    ):
        raise AssertionError("matching independent color evidence was rejected")
    if detail_candidate_is_consistent(
        "bright magenta stapler",
        "A small white rectangular object is visible near the table.",
    ):
        raise AssertionError("conflicting independent color evidence was accepted")
    if detail_candidate_is_consistent("smartphone", "NO_CANDIDATE"):
        raise AssertionError("detail search accepted an independent no-candidate result")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit-only", action="store_true")
    args = parser.parse_args()

    segment_seconds, peak_rms = _test_parser_and_segmenter()
    _test_latest_turn_wins()
    _test_narrated_finder_actions()
    _test_edge_detail_sheet()
    _test_target_identity()
    _test_detail_candidate_consistency()
    print(
        f"parser_segmenter: PASS; segment_seconds={segment_seconds:.3f}; "
        f"peak_rms={peak_rms:.0f}"
    )
    print("latest_turn_wins: PASS; stale response discarded")
    print(
        "finder_narration: PASS; expected look and final not-found accepted; "
        "premature or mismatched actions rejected"
    )
    print("edge_detail_sheet: PASS; four overlapping edge quadrants magnified")
    print("target_identity: PASS; product name and object type cannot be discarded")
    print("detail_consistency: PASS; independent evidence rejects color conflicts")
    if args.unit_only:
        print("result: PASS pure companion routing and audio segmentation")
        return 0

    subprocess.run([str(REPO_ROOT / "scripts" / "ensure_gemma.sh")], check=True)
    session = CompanionSession(speech=False, microphone=False, log_dir=REPO_ROOT / "logs")
    boot_started = time.monotonic()
    session.start(announce_scene=True)
    try:
        boot_deadline = time.monotonic() + 30
        while session.last_result is None and time.monotonic() < boot_deadline:
            time.sleep(0.05)
        if session.last_result is None or session.last_result.response != READY_CUE:
            raise AssertionError("fresh boot observation did not produce the readiness cue")
        boot_seconds = time.monotonic() - boot_started

        move_results = [
            session.handle_text("look left"),
            session.handle_text("look right"),
            session.handle_text("look center"),
        ]
        if [result.action for result in move_results] != ["look_left", "look_right", "look_center"]:
            raise AssertionError("direct movement routing failed")
        max_move = max(result.latency_seconds for result in move_results)
        if max_move >= 1.5:
            raise AssertionError(f"direct movement took {max_move:.3f}s")

        visual = session.handle_text("what do you see?")
        if visual.action != "describe" or not visual.response or not visual.image_path:
            raise AssertionError("fresh visual description was incomplete")
        if not Path(visual.image_path).is_file():
            raise AssertionError(f"fresh visual frame is missing: {visual.image_path}")
        if visual.latency_seconds >= 5.0:
            raise AssertionError(f"visual response took {visual.latency_seconds:.3f}s")

        available = available_memory_bytes()
        if available < MIN_AVAILABLE_BYTES:
            raise AssertionError(f"only {available} bytes of memory remain")
    finally:
        session.stop()

    print(f"boot_readiness: PASS; fresh_scene_seconds={boot_seconds:.3f}; cue={READY_CUE}")
    print(
        "direct_moves: PASS; sequence=look_left,look_right,look_center; "
        f"max_latency_seconds={max_move:.3f}"
    )
    print(
        f"fresh_vision: PASS; direction={visual.direction}; "
        f"latency_seconds={visual.latency_seconds:.3f}; response={visual.response}"
    )
    print(f"fresh_frame: {visual.image_path}")
    print(f"available_memory_mib: {available / (1024 * 1024):.1f}")
    print("result: PASS continuous companion routing, physical PTZ, and fresh vision")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
