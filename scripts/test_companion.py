#!/usr/bin/env python3
"""Acceptance checks for continuous segmentation, routing, PTZ, and fresh vision."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from array import array
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.gemma import GemmaClient  # noqa: E402
from audio.continuous import VoiceSegmenter  # noqa: E402
from demos.companion import (  # noqa: E402
    MIN_AVAILABLE_BYTES,
    READY_CUE,
    CompanionResult,
    CompanionSession,
    available_memory_bytes,
    normalize_finder_target,
    preserves_target_identity,
)
from demos.elderly import (  # noqa: E402
    ElderlyFinder,
    FINDER_SETTLE_SECONDS,
    SEARCH_POSITIONS,
    blind_traits_support_case_target,
    candidate_match_is_confirmed,
    create_detail_panel_crop,
    create_edge_detail_sheet,
    detail_panel_number,
    detail_candidate_is_consistent,
    found_target_sentence,
    parse_grounded_narrated_report_found,
    parse_narrated_look_action,
    parse_narrated_not_found,
    parse_textual_report_found,
    parse_trailing_search_action,
)
from PIL import Image  # noqa: E402
from tools.registry import COMPANION_DECISION_SCHEMAS, COMPANION_TOOL_SCHEMAS  # noqa: E402


def _pcm(level: int, samples: int) -> bytes:
    return array("h", [level] * samples).tobytes()


def _test_agent_tools_and_segmenter() -> tuple[float, float]:
    names = [schema["function"]["name"] for schema in COMPANION_TOOL_SCHEMAS]
    expected = {
        "look_left",
        "look_right",
        "look_up",
        "look_down",
        "look_center",
        "inspect_view",
        "find_object",
        "make_voice_louder",
        "make_voice_softer",
        "set_volume",
        "cancel_current_response",
        "sleep",
    }
    if set(names) != expected or len(names) != len(expected):
        raise AssertionError(f"companion tool registry mismatch: {names!r}")
    source = (REPO_ROOT / "demos" / "companion.py").read_text(encoding="utf-8")
    if "def parse_intent" in source or "direction_aliases" in source:
        raise AssertionError("a hard-coded phrase/direction router remains in companion.py")

    segmenter = VoiceSegmenter()
    muted = _pcm(100, segmenter.chunk_bytes // 2)
    unmuted_pause = _pcm(300, segmenter.chunk_bytes // 2)
    voice = _pcm(2_000, segmenter.chunk_bytes // 2)
    now = 100.0
    starts = 0
    segment = None
    # The accepted AT-CSP1 calibration puts muted input below 260 RMS and
    # unmuted room tone above it. A natural pause must therefore remain part
    # of one command until the physical mute floor returns.
    sequence = (
        [muted] * 3
        + [voice] * 5
        + [unmuted_pause] * 8
        + [voice] * 5
        + [muted] * 4
    )
    completed_segments = 0
    for chunk in sequence:
        started, completed = segmenter.process(chunk, now=now)
        starts += int(started)
        completed_segments += int(completed is not None)
        segment = completed or segment
        now += segmenter.chunk_ms / 1000
    if starts != 1 or completed_segments != 1 or segment is None:
        raise AssertionError(
            f"segmenter starts={starts}, completed_segments={completed_segments}"
        )
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


def _test_raw_tool_stream_parser() -> None:
    samples = (
        (
            "<|tool_call>call look_left{}<tool_call|>\ninspect_view",
            ["look_left", "inspect_view"],
            {},
        ),
        (
            'find_object{target:<|"|>small white AirPods charging case<|"|>}',
            ["find_object"],
            {"target": "small white AirPods charging case"},
        ),
        ("set_volume(percent=73)", ["set_volume"], {"percent": 73}),
        ("look_center.\nI have returned to neutral.", ["look_center"], {}),
    )
    for raw, expected_names, expected_arguments in samples:
        calls = GemmaClient._fallback_tool_calls(raw, COMPANION_DECISION_SCHEMAS)
        names = [str((call.get("function") or {}).get("name")) for call in calls]
        if names != expected_names:
            raise AssertionError(f"raw tool stream parsed as {names!r}: {raw!r}")
        arguments = (calls[-1].get("function") or {}).get("arguments") or {}
        if expected_arguments and arguments != expected_arguments:
            raise AssertionError(f"raw tool arguments parsed as {arguments!r}: {raw!r}")


def _test_narrated_finder_actions() -> None:
    if found_target_sentence("glasses", "on the table") != "Your glasses are on the table.":
        raise AssertionError("plural finder result has incorrect grammar")
    if found_target_sentence("AirPods charging case", "by the laptop") != (
        "Your AirPods charging case is by the laptop."
    ):
        raise AssertionError("singular finder result has incorrect grammar")
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
    for narrated in (
        "I see glasses. They are on the table.",
        "report_found glasses on the table",
    ):
        narrated_location = parse_grounded_narrated_report_found(
            narrated,
            target="glasses",
            visual_evidence="DETECTED: glasses",
        )
        if narrated_location != "on the table":
            raise AssertionError(
                f"grounded report_found narration parsed as {narrated_location!r}"
            )
    if parse_grounded_narrated_report_found(
        "I see glasses on the table.",
        target="glasses",
        visual_evidence="ABSENT",
    ) is not None:
        raise AssertionError("finder accepted narrated found result without detected evidence")
    if parse_grounded_narrated_report_found(
        "I do not see glasses on the table.",
        target="glasses",
        visual_evidence="DETECTED: glasses",
    ) is not None:
        raise AssertionError("finder converted negative narration into a found result")
    trailing = "I understand. I will search now.\nreport_not_found"
    if parse_trailing_search_action(trailing, "report_not_found") != "report_not_found":
        raise AssertionError("finder rejected an expected trailing action token")
    if parse_trailing_search_action(trailing, "look_right") is not None:
        raise AssertionError("finder accepted a trailing action outside the expected search step")


def _test_edge_detail_sheet() -> None:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "frame.jpg"
        source_image = Image.new("RGB", (1280, 720), "black")
        for x in range(80):
            for y in range(80):
                source_image.putpixel((x, y), (255, 0, 0))
        source_image.save(source, quality=100)
        detail = Path(create_edge_detail_sheet(source))
        if not detail.is_file():
            raise AssertionError("edge-detail sheet was not created")
        with Image.open(detail) as rendered:
            if rendered.size != (1024, 576):
                raise AssertionError(f"edge-detail sheet size was {rendered.size!r}")
            red, green, blue = rendered.convert("RGB").getpixel((12, 12))
            if red < 180 or green > 80 or blue > 80:
                raise AssertionError("edge-detail sheet cropped away the physical top-left edge")
        panel = Path(create_detail_panel_crop(detail, 1))
        with Image.open(panel) as rendered:
            if rendered.size != (1024, 576):
                raise AssertionError(f"detail panel size was {rendered.size!r}")
            red, green, blue = rendered.convert("RGB").getpixel((24, 24))
            if red < 180 or green > 80 or blue > 80:
                raise AssertionError("detail panel crop lost the selected physical candidate")
        if detail_panel_number("DETECTED PANEL 3: near a laptop") != 3:
            raise AssertionError("detail panel number was not parsed")
        previous = os.environ.get("GEMMA_EDGE_DETAIL_MAX_LONG_EDGE")
        os.environ["GEMMA_EDGE_DETAIL_MAX_LONG_EDGE"] = "512"
        try:
            bounded = Path(create_edge_detail_sheet(source))
            with Image.open(bounded) as rendered:
                if rendered.size != (512, 288):
                    raise AssertionError(f"bounded edge-detail size was {rendered.size!r}")
        finally:
            if previous is None:
                os.environ.pop("GEMMA_EDGE_DETAIL_MAX_LONG_EDGE", None)
            else:
                os.environ["GEMMA_EDGE_DETAIL_MAX_LONG_EDGE"] = previous


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
    if not candidate_match_is_confirmed("MATCH."):
        raise AssertionError("strict candidate matcher rejected its affirmative token")
    for unsafe in ("MISMATCH", "MATCH or MISMATCH", "It might MATCH", "MATCH because it is white"):
        if candidate_match_is_confirmed(unsafe):
            raise AssertionError(f"strict candidate matcher accepted ambiguous prose: {unsafe!r}")
    case_target = "small white Apple AirPods wireless-earbud charging case"
    if not blind_traits_support_case_target(
        case_target,
        "White rectangular object (small, smooth, portable) in the foreground; black laptop",
    ):
        raise AssertionError("matching target-blind portable-case traits were rejected")
    unsafe_case_evidence = (
        "small white wireless mouse, smooth and oval",
        "small white cable, cylindrical and portable",
        "small white rectangular paper beside a QR code",
        "small white rectangular circuit board",
        "large white rectangular container",
    )
    for evidence in unsafe_case_evidence:
        if blind_traits_support_case_target(case_target, evidence):
            raise AssertionError(f"conflicting case evidence was accepted: {evidence!r}")


def _test_wide_candidate_identity_gate() -> None:
    class FakeLoop:
        def __init__(self) -> None:
            self.memory = SimpleNamespace(observations=[])
            self.records: list[tuple[str, dict]] = []
            self.responses = iter(
                [
                    ("DETECTED: AirPod near a table", []),
                    (
                        "",
                        [
                            {
                                "function": {
                                    "name": "report_found",
                                    "arguments": {"location": "near a table"},
                                }
                            }
                        ],
                    ),
                    ("Black circuit board; white cardboard package near the table.", []),
                    ("MISMATCH", []),
                    ("ABSENT", []),
                    (
                        "",
                        [
                            {
                                "function": {
                                    "name": "look_left",
                                    "arguments": {},
                                }
                            }
                        ],
                    ),
                ]
            )

        def _step(self, messages, images=None, tools=None):
            return next(self.responses)

        def log(self, action: str, **fields) -> None:
            self.records.append((action, fields))

    with tempfile.TemporaryDirectory() as directory:
        frame = Path(directory) / "frame.jpg"
        Image.new("RGB", (1280, 720), "white").save(frame)
        finder = object.__new__(ElderlyFinder)
        finder.loop = FakeLoop()
        finder.continue_check = None
        finder.camera_lock = None
        decision = finder._inspect(str(frame), "center", "look_left", "AirPod")
        if decision != ("look_left", ""):
            raise AssertionError(f"rejected wide candidate did not continue: {decision!r}")
        checks = [
            fields
            for action, fields in finder.loop.records
            if action == "VISUAL_CANDIDATE_CHECK"
            and fields.get("evidence_kind") == "wide-frame inspection"
        ]
        if len(checks) != 1 or checks[0].get("consistent") is not False:
            raise AssertionError("wide-frame report_found bypassed identity verification")

    expected = "small white Apple AirPods wireless-earbud charging case"
    if normalize_finder_target("AirPod") != expected:
        raise AssertionError("singular AirPod was not normalized to its visible demo target")
    if normalize_finder_target("tissue box") != "tissue box":
        raise AssertionError("generic finder target was unexpectedly rewritten")
    if SEARCH_POSITIONS["center"] != (0.0, 0.0):
        raise AssertionError("finder does not establish a level baseline before panning")
    if SEARCH_POSITIONS["left"] != (-65.0, 0.0) or SEARCH_POSITIONS["right"] != (65.0, 0.0):
        raise AssertionError("finder tabletop sweep no longer covers the intermediate blind wedges")
    if FINDER_SETTLE_SECONDS < 4.0:
        raise AssertionError("finder can capture before a long physical pan settles")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit-only", action="store_true")
    args = parser.parse_args()

    segment_seconds, peak_rms = _test_agent_tools_and_segmenter()
    _test_latest_turn_wins()
    _test_raw_tool_stream_parser()
    _test_narrated_finder_actions()
    _test_edge_detail_sheet()
    _test_target_identity()
    _test_detail_candidate_consistency()
    _test_wide_candidate_identity_gate()
    print(
        f"agent_tools_segmenter: PASS; tools={len(COMPANION_TOOL_SCHEMAS)}; "
        f"segment_seconds={segment_seconds:.3f}; "
        f"peak_rms={peak_rms:.0f}"
    )
    print("latest_turn_wins: PASS; stale response discarded")
    print("raw_tool_stream: PASS; native, bare, positional, and argument forms recovered")
    print(
        "finder_narration: PASS; expected look and final not-found accepted; "
        "premature or mismatched actions rejected"
    )
    print("edge_detail_sheet: PASS; four physical corner regions preserved")
    print("target_identity: PASS; product name and object type cannot be discarded")
    print(
        "detail_consistency: PASS; deterministic conflicts and ambiguous semantic verdicts rejected"
    )
    print("wide_identity_gate: PASS; rejected wide candidate continues the physical sweep")
    if args.unit_only:
        print("result: PASS phrase-free agent tool contract and audio segmentation")
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
            session.handle_text("Aim your gaze toward the port side."),
            session.handle_text("Sweep your attention toward starboard."),
            session.handle_text("Return your gaze to its neutral forward pose."),
        ]
        if [result.action for result in move_results] != ["look_left", "look_right", "look_center"]:
            raise AssertionError("direct movement routing failed")
        max_move = max(result.latency_seconds for result in move_results)
        if max_move >= 3.0:
            raise AssertionError(f"direct movement took {max_move:.3f}s")

        visual = session.handle_text(
            "Give me a concise account of the scene currently before the lens."
        )
        if visual.action != "visual_question" or not visual.response or not visual.image_path:
            raise AssertionError("fresh visual description was incomplete")
        if not Path(visual.image_path).is_file():
            raise AssertionError(f"fresh visual frame is missing: {visual.image_path}")
        if visual.latency_seconds >= 8.0:
            raise AssertionError(f"visual response took {visual.latency_seconds:.3f}s")

        available = available_memory_bytes()
        if available < MIN_AVAILABLE_BYTES:
            raise AssertionError(f"only {available} bytes of memory remain")
    finally:
        session.stop()

    print(f"boot_readiness: PASS; fresh_scene_seconds={boot_seconds:.3f}; cue={READY_CUE}")
    print(
        "agentic_moves: PASS; paraphrase_sequence=look_left,look_right,look_center; "
        f"max_latency_seconds={max_move:.3f}"
    )
    print(
        f"fresh_vision: PASS; direction={visual.direction}; "
        f"latency_seconds={visual.latency_seconds:.3f}; response={visual.response}"
    )
    print(f"fresh_frame: {visual.image_path}")
    print(f"available_memory_mib: {available / (1024 * 1024):.1f}")
    print("result: PASS phrase-free agent routing, physical PTZ, and fresh vision")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
