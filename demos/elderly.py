"""Voice-first, safety-bounded misplaced-object finder."""

from __future__ import annotations

import json
import re
import threading
import time
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps

from agent.gemma import GemmaClient
from agent.loop import AgentLoop, AgentLoopError
from agent.prompts import AGENT_CORE, ELDERLY_PROMPT
from audio.tts import (
    ELDERLY_NOT_FOUND,
    FIXED_PHRASES,
    GLASSES_CONFIRMATION,
    ONE_MOMENT,
    prerender,
    speak,
)
from camera.obsbot import look_at
from tools.registry import (
    REPORT_FOUND_SCHEMA,
    REPORT_NOT_FOUND_SCHEMA,
    look_schema,
    tool_name,
)

SEARCH_ORDER = ("center", "left", "right", "up", "down")
LOOK_FOR_DIRECTION = {direction: f"look_{direction}" for direction in SEARCH_ORDER}
SEARCH_POSITIONS = {
    # Start on the front tabletop, where small everyday objects are normally placed.
    "center": (0.0, -25.0),
    "left": (-120.0, -25.0),
    "right": (120.0, -25.0),
    "up": (0.0, 25.0),
    "down": (0.0, -30.0),
}
MEDICAL_WORDS = {
    "dose",
    "dosage",
    "medicine",
    "medication",
    "pill",
    "emergency",
    "symptom",
    "diagnose",
    "doctor",
}
VISUAL_CLASSIFIER_PROMPT = (
    "You are a visual classifier. Inspect the attached pixels now. "
    "Never state plans or future actions."
)
TARGET_COLORS = {
    "black",
    "blue",
    "brown",
    "gold",
    "gray",
    "green",
    "grey",
    "magenta",
    "orange",
    "pink",
    "purple",
    "red",
    "silver",
    "white",
    "yellow",
}


def is_medical_request(text: str) -> bool:
    return bool(set(re.findall(r"[a-z]+", text.lower())) & MEDICAL_WORDS)


def medical_refusal() -> str:
    return "I can't help with medical advice; please ask a caregiver or doctor."


def detail_candidate_is_consistent(target: str, independent_evidence: str) -> bool:
    """Apply deterministic rejection gates before semantic identity verification."""

    normalized = independent_evidence.upper()
    if "NO_CANDIDATE" in normalized or "NO OBJECT" in normalized:
        return False
    target_words = set(re.findall(r"[a-z]+", target.casefold()))
    evidence_words = set(re.findall(r"[a-z]+", independent_evidence.casefold()))
    required_colors = target_words & TARGET_COLORS
    return not required_colors or bool(required_colors & evidence_words)


def candidate_match_is_confirmed(model_text: str) -> bool:
    """Accept only the verifier's exact affirmative token."""

    return bool(re.fullmatch(r"\s*MATCH\s*[.!]?\s*", model_text, flags=re.IGNORECASE))


def create_edge_detail_sheet(image_path: str | Path) -> str:
    """Magnify the four overlapping edge quadrants of one physical observation."""

    source_path = Path(image_path)
    output_path = source_path.with_name(f"{source_path.stem}-edge-detail.jpg")
    temporary_path = output_path.with_name(f"{output_path.stem}.tmp.jpg")
    with Image.open(source_path) as source:
        frame = source.convert("RGB")
        width, height = frame.size
        edge_width = max(1, round(width * 0.32))
        edge_height = max(1, round(height * 0.68))
        boxes = (
            (0, 0, edge_width, edge_height),
            (width - edge_width, 0, width, edge_height),
            (0, height - edge_height, edge_width, height),
            (width - edge_width, height - edge_height, width, height),
        )
        sheet = Image.new("RGB", (1024, 576))
        for index, box in enumerate(boxes):
            detail = ImageOps.fit(frame.crop(box), (512, 288))
            sheet.paste(detail, ((index % 2) * 512, (index // 2) * 288))
        try:
            sheet.save(temporary_path, format="JPEG", quality=92)
            if temporary_path.stat().st_size < 1024:
                raise OSError("generated edge-detail JPEG is unexpectedly small")
            temporary_path.replace(output_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
    return str(output_path)


@dataclass(frozen=True)
class FinderResult:
    found: bool
    direction: str | None
    location: str
    gemma_moves: tuple[str, ...]
    duration_seconds: float
    log_path: str


class FinderCancelled(AgentLoopError):
    """Raised when a newer spoken turn invalidates an active object search."""


def parse_narrated_look_action(model_text: str, expected_tool: str | None) -> str | None:
    """Accept a narrated look only when it matches the bounded search's next tool."""

    if expected_tool is None or not expected_tool.startswith("look_"):
        return None
    direction = re.escape(expected_tool.removeprefix("look_"))
    narrated = re.search(
        rf"\b(?:will|next|now|start(?:ing)?|continue|then)\b"
        rf"[^\n.!?]{{0,80}}\blook(?:ing)?(?:\s+at)?\s+(?:the\s+)?{direction}\b",
        model_text,
        flags=re.IGNORECASE,
    )
    return expected_tool if narrated else None


def parse_narrated_not_found(model_text: str, *, final_direction: bool) -> str | None:
    """Accept an honest narrated miss only after the bounded search is complete."""

    if not final_direction:
        return None
    negative_result = re.search(
        r"\b(?:(?:did|do|does|could|can)\s+not|didn't|doesn't|couldn't|can't|cannot|was\s+unable\s+to)\s+"
        r"(?:find|see|locate)\b|\b(?:not\s+found|no\s+matching\s+object)\b",
        model_text,
        flags=re.IGNORECASE,
    )
    return "report_not_found" if negative_result else None


def parse_trailing_search_action(model_text: str, expected_tool: str) -> str | None:
    """Accept an expected tool name serialized alone on the final response line."""

    trailing = re.search(
        rf"(?:^|\n)\s*{re.escape(expected_tool)}\s*$",
        model_text,
        flags=re.IGNORECASE,
    )
    return expected_tool if trailing else None


def parse_textual_report_found(model_text: str) -> str | None:
    """Parse llama.cpp's occasional textual serialization of report_found."""

    match = re.fullmatch(
        r"\s*report_found\s*\{\s*location\s*:\s*(.+?)\s*\}\s*",
        model_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        return None
    location = match.group(1).replace('<|"|>', "").strip().strip("\"'").strip()
    if not location:
        return None
    physical_anchors = (
        "table",
        "desk",
        "chair",
        "laptop",
        "cable",
        "cup",
        "bag",
        "phone",
        "smartphone",
        "surface",
    )
    if not any(anchor in location.casefold() for anchor in physical_anchors):
        return None
    return re.sub(r"\bsurface\b", "tabletop", location, flags=re.IGNORECASE)


class ElderlyFinder:
    def __init__(
        self,
        *,
        speech: bool = True,
        log_dir: str | Path | None = None,
        gemma: GemmaClient | None = None,
        say_callback: Callable[[str], None] | None = None,
        continue_check: Callable[[], bool] | None = None,
        camera_lock: threading.Lock | None = None,
    ) -> None:
        self.speech = speech
        self.loop = AgentLoop(gemma=gemma, log_dir=log_dir)
        self.say_callback = say_callback
        self.continue_check = continue_check
        self.camera_lock = camera_lock

    def _checkpoint(self) -> None:
        if self.continue_check is not None and not self.continue_check():
            raise FinderCancelled("a newer user turn cancelled the object search")

    def _say(self, text: str) -> None:
        self._checkpoint()
        clean = " ".join(text.split())
        print(f"Gemma: {clean}", flush=True)
        self.loop.log("SAY", text=clean)
        if self.say_callback is not None:
            self.say_callback(clean)
        elif self.speech:
            speak(clean, words_per_minute=120)
        self._checkpoint()

    def _move_to(self, direction: str, *, issued_by_gemma: bool) -> tuple[float, float]:
        self._checkpoint()
        pan, tilt = SEARCH_POSITIONS[direction]
        started = time.monotonic()
        guard = self.camera_lock if self.camera_lock is not None else nullcontext()
        with guard:
            position = look_at(pan, tilt)
            time.sleep(0.8)
        self.loop.log(
            "LOOK" if issued_by_gemma else "SEARCH_START_MOVE",
            tool=LOOK_FOR_DIRECTION[direction],
            direction=direction,
            pan_degrees=position[0],
            tilt_degrees=position[1],
            issued_by="Gemma" if issued_by_gemma else "fixed-start",
            latency_seconds=round(time.monotonic() - started, 3),
        )
        self._checkpoint()
        return position

    def _observe(self, direction: str) -> str:
        self._checkpoint()
        guard = self.camera_lock if self.camera_lock is not None else nullcontext()
        with guard:
            image_path = self.loop.observe(direction)
        self._checkpoint()
        return image_path

    @staticmethod
    def _argument(call: dict, key: str) -> str:
        arguments = (call.get("function") or {}).get("arguments") or {}
        return " ".join(str(arguments.get(key) or "").split())

    def _ground_location(self, location: str, target: str, visual_evidence: str) -> str:
        """Normalize one found location into short furniture-relative speech."""

        clean = " ".join(location.split()).strip()
        if "|" in clean:
            cells = [
                cell.strip()
                for cell in re.findall(r"\|\s*([^|]+?)\s*(?=\|)", clean)
                if cell.strip() and not re.fullmatch(r"[-: ]+", cell.strip())
            ]
            if cells:
                clean = cells[-1]
        physical_anchors = (
            "table",
            "desk",
            "chair",
            "laptop",
            "cable",
            "cup",
            "bag",
            "phone",
            "smartphone",
        )
        if (
            not clean
            or "image" in clean.casefold()
            or not any(anchor in clean.casefold() for anchor in physical_anchors)
        ):
            refined, _ = self.loop._step(
                [
                    {
                        "role": "system",
                        "content": "Rewrite visual locations in plain furniture-relative language.",
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Target: {target}. Grounded visual evidence: {visual_evidence}. "
                            f"Original location wording: {clean}. Reply with only a short physical "
                            "location using a table, chair, laptop, cable, or another nearby object. "
                            "Never use markdown, a table, the word image, or the word camera."
                        ),
                    },
                ]
            )
            clean = " ".join(refined.split()).rstrip(".")
        return re.sub(r"\bsurface\b", "tabletop", clean, flags=re.IGNORECASE)

    def _resolve_decision(
        self,
        model_text: str,
        calls: list[dict],
        *,
        next_tool: str | None,
        target: str,
        visual_evidence: str,
    ) -> tuple[str, str] | None:
        if calls:
            call = calls[0]
            action = tool_name(call)
            if action == "report_found":
                location = self._ground_location(
                    self._argument(call, "location"), target, visual_evidence
                )
                return action, location
            if action == next_tool or (next_tool is None and action == "report_not_found"):
                return action, ""
            return None

        textual_location = parse_textual_report_found(model_text)
        if textual_location is not None:
            location = self._ground_location(textual_location, target, visual_evidence)
            self.loop.log(
                "PARSED_TEXT_ACTION",
                tool="report_found",
                text=model_text,
                location=location,
            )
            return "report_found", location
        match = re.match(r"^FOUND:\s*(.+)$", model_text, flags=re.IGNORECASE)
        if match:
            location = self._ground_location(match.group(1).strip(), target, visual_evidence)
            self.loop.log(
                "PARSED_TEXT_ACTION", tool="report_found", text=model_text, location=location
            )
            return "report_found", location
        if model_text.upper().startswith("NOT_FOUND"):
            fallback_action = next_tool or "report_not_found"
            self.loop.log("PARSED_TEXT_ACTION", tool=fallback_action, text=model_text)
            return fallback_action, ""
        plain_action = model_text.strip().lower().strip("` .")
        if plain_action == next_tool or (next_tool is None and plain_action == "report_not_found"):
            self.loop.log("PARSED_TEXT_ACTION", tool=plain_action, text=model_text)
            return plain_action, ""
        expected_action = next_tool or "report_not_found"
        trailing_action = parse_trailing_search_action(model_text, expected_action)
        if trailing_action is not None:
            self.loop.log("PARSED_TEXT_ACTION", tool=trailing_action, text=model_text)
            return trailing_action, ""
        narrated_action = parse_narrated_look_action(model_text, next_tool)
        if narrated_action is not None:
            self.loop.log(
                "PARSED_NARRATED_ACTION",
                tool=narrated_action,
                expected_tool=next_tool,
                text=model_text,
            )
            return narrated_action, ""
        narrated_not_found = parse_narrated_not_found(
            model_text,
            final_direction=next_tool is None,
        )
        if narrated_not_found is not None:
            self.loop.log(
                "PARSED_NARRATED_ACTION",
                tool=narrated_not_found,
                expected_tool="report_not_found",
                text=model_text,
            )
            return narrated_not_found, ""
        return None

    def _decide_from_evidence(
        self,
        *,
        visual_evidence: str,
        direction: str,
        checked: str,
        next_tool: str | None,
        target: str,
        continuation: str,
        tools: list[dict],
        evidence_kind: str,
        allow_unparseable: bool = False,
    ) -> tuple[str, str] | None:
        decision_prompt = f"""Request: find the user's {target}.
Current direction: {direction}. Previously inspected: {checked}.
Grounded evidence from your just-completed {evidence_kind}: {visual_evidence}
Report the requested object only if that evidence clearly describes a candidate matching its physical appearance and type.
If found, call report_found with one simple physical location naming nearby furniture or objects; never say a side of the image or a detail panel.
{continuation}
Call exactly one supplied tool and do not invent a location."""
        model_text, calls = self.loop._step(
            [
                {"role": "system", "content": f"{AGENT_CORE}\n\n{ELDERLY_PROMPT}"},
                {"role": "user", "content": decision_prompt},
            ],
            tools=tools,
        )
        self._checkpoint()
        resolved = self._resolve_decision(
            model_text,
            calls,
            next_tool=next_tool,
            target=target,
            visual_evidence=visual_evidence,
        )
        if resolved is not None:
            return resolved

        valid_miss = next_tool or "report_not_found"
        retry_prompt = f"""Your previous action response was invalid: {model_text}
The current direction {direction} has already been inspected.
If the grounded evidence clearly shows the requested {target}, call report_found with one plain physical location.
Otherwise call {valid_miss}. That is the only valid search continuation.
Call exactly one supplied tool. Do not narrate, repeat a direction, or use markdown."""
        retry_text, retry_calls = self.loop._step(
            [
                {"role": "system", "content": f"{AGENT_CORE}\n\n{ELDERLY_PROMPT}"},
                {"role": "user", "content": retry_prompt},
            ],
            tools=tools,
        )
        self._checkpoint()
        self.loop.log(
            "FINDER_DECISION_RETRY",
            direction=direction,
            evidence_kind=evidence_kind,
            expected_tool=valid_miss,
            first_text=model_text,
            retry_text=retry_text,
            retry_tool_calls=len(retry_calls),
        )
        resolved = self._resolve_decision(
            retry_text,
            retry_calls,
            next_tool=next_tool,
            target=target,
            visual_evidence=visual_evidence,
        )
        if resolved is not None:
            return resolved
        if allow_unparseable:
            self.loop.log(
                "FINDER_OPTIONAL_DECISION_INVALID",
                direction=direction,
                evidence_kind=evidence_kind,
                first_text=model_text,
                retry_text=retry_text,
            )
            return None
        raise AgentLoopError(
            f"Gemma returned no parseable finder action after retry: {model_text!r}; "
            f"retry={retry_text!r}"
        )

    def _verify_candidate_identity(
        self,
        *,
        image_path: str,
        direction: str,
        target: str,
        target_aware_evidence: str,
        evidence_kind: str,
    ) -> bool:
        """Cross-check a detection using target-blind pixels and strict text matching."""

        independent_evidence, _ = self.loop._step(
            [
                {
                    "role": "system",
                    "content": (
                        "You are a target-blind visual observer. Inspect only the attached "
                        "pixels. Do not guess brands or identities."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "In one semicolon-separated line of at most 50 words, list every distinct "
                        "small physical object you can actually see. Include observed color, "
                        "shape, object type, nearby anchor, and uncertainty. If no small object "
                        "is clear, reply exactly NO_CANDIDATE."
                    ),
                },
            ],
            [image_path],
        )
        self._checkpoint()
        deterministic_consistency = detail_candidate_is_consistent(
            target, independent_evidence
        )
        match_text = "MISMATCH"
        if deterministic_consistency:
            match_text, _ = self.loop._step(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a strict evidence auditor. Decide whether a target-blind "
                            "observation explicitly and unambiguously supports the requested "
                            "object's physical category. Similar color or shape is insufficient. "
                            "Uncertainty, an alternative object type, a generic object, or a "
                            "missing product category requires MISMATCH. Reply exactly MATCH or "
                            "MISMATCH."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Requested object: {target}\n"
                            f"Target-blind observation: {independent_evidence}"
                        ),
                    },
                ]
            )
            self._checkpoint()
        consistent = deterministic_consistency and candidate_match_is_confirmed(match_text)
        self.loop.log(
            "VISUAL_CANDIDATE_CHECK",
            direction=direction,
            target=target,
            evidence_kind=evidence_kind,
            target_aware_evidence=target_aware_evidence,
            independent_evidence=independent_evidence,
            deterministic_consistency=deterministic_consistency,
            matcher_evidence=match_text,
            consistent=consistent,
        )
        return consistent

    def _inspect(
        self,
        image_path: str,
        direction: str,
        next_tool: str | None,
        target: str,
    ) -> tuple[str, str]:
        self._checkpoint()
        checked = ", ".join(
            item.direction for item in self.loop.memory.observations
        ) or "none"
        if next_tool:
            continuation = f"If the requested object is not clearly visible, call {next_tool} to continue the systematic search."
            tools = [REPORT_FOUND_SCHEMA, look_schema(next_tool)]
        else:
            continuation = "This is the final direction. If the requested object is not clearly visible, call report_not_found."
            tools = [REPORT_FOUND_SCHEMA, REPORT_NOT_FOUND_SCHEMA]
        vision_prompt = f"""Target: {target}.
Inspect only this fresh {direction} camera frame. A partly clipped target counts, and unreadable brand text does not rule out a physically matching common product.
Do not substitute a merely similar object or infer anything outside the frame.
Answer exactly DETECTED: followed by its physical location near a table, chair, laptop, cable, or other nearby object, or ABSENT if no matching target is visible."""
        visual_evidence, _ = self.loop._step(
            [
                {"role": "system", "content": VISUAL_CLASSIFIER_PROMPT},
                {"role": "user", "content": vision_prompt},
            ],
            [image_path],
        )
        self._checkpoint()
        self.loop.log(
            "VISUAL_EVIDENCE",
            direction=direction,
            target=target,
            text=visual_evidence,
        )

        wide_decision = self._decide_from_evidence(
            visual_evidence=visual_evidence,
            direction=direction,
            checked=checked,
            next_tool=next_tool,
            target=target,
            continuation=continuation,
            tools=tools,
            evidence_kind="wide-frame inspection",
        )
        if wide_decision[0] == "report_found":
            return wide_decision

        try:
            detail_path = create_edge_detail_sheet(image_path)
        except OSError as exc:
            self.loop.log(
                "EDGE_DETAIL_FALLBACK",
                direction=direction,
                source_image=image_path,
                error=str(exc),
            )
            return wide_decision
        self.loop.log(
            "EDGE_DETAIL_CREATED",
            direction=direction,
            source_image=image_path,
            detail_image=detail_path,
        )
        detail_prompt = f"""Target: a {target}. Answer exactly DETECTED: followed by its physical location near a table or laptop, or ABSENT if no matching target is visible. A partially clipped target counts."""
        detail_evidence, _ = self.loop._step(
            [
                {"role": "system", "content": VISUAL_CLASSIFIER_PROMPT},
                {"role": "user", "content": detail_prompt},
            ],
            [detail_path],
        )
        self._checkpoint()
        self.loop.log(
            "EDGE_DETAIL_EVIDENCE",
            direction=direction,
            target=target,
            source_image=image_path,
            detail_image=detail_path,
            text=detail_evidence,
        )
        if detail_evidence.upper().startswith("DETECTED:"):
            if not self._verify_candidate_identity(
                image_path=detail_path,
                direction=direction,
                target=target,
                target_aware_evidence=detail_evidence,
                evidence_kind="magnified edge-detail inspection",
            ):
                return wide_decision
        detail_decision = self._decide_from_evidence(
            visual_evidence=detail_evidence,
            direction=direction,
            checked=checked,
            next_tool=next_tool,
            target=target,
            continuation=continuation,
            tools=tools,
            evidence_kind="magnified edge-detail inspection",
            allow_unparseable=True,
        )
        if detail_decision is not None and detail_decision[0] == "report_found":
            return detail_decision
        return wide_decision

    def search_live(
        self,
        request: str = "Please find my glasses",
        *,
        target: str = "wearable eyeglasses",
    ) -> FinderResult:
        if self.speech:
            prerender(FIXED_PHRASES)
        if is_medical_request(request):
            refusal = medical_refusal()
            self._say(refusal)
            self.loop.log("SAFETY_REFUSAL", request=request, response=refusal)
            return FinderResult(False, None, refusal, (), 0.0, str(self.loop.log_path))

        started = time.monotonic()
        self._checkpoint()
        confirmation = (
            GLASSES_CONFIRMATION
            if target.casefold() in {"glasses", "wearable eyeglasses"}
            else f"You want me to find the {target}, is that right?"
        )
        self._say(confirmation)
        self._say(ONE_MOMENT)
        self.loop.log("FINDER_START", request=request, target=target)
        gemma_moves: list[str] = []

        self._move_to("center", issued_by_gemma=False)
        direction_index = 0
        while direction_index < len(SEARCH_ORDER):
            direction = SEARCH_ORDER[direction_index]
            image_path = self._observe(direction)
            self.loop.memory.remember(direction, image_path, f"inspected for {target}")
            next_tool = (
                LOOK_FOR_DIRECTION[SEARCH_ORDER[direction_index + 1]]
                if direction_index + 1 < len(SEARCH_ORDER)
                else None
            )
            action, location = self._inspect(image_path, direction, next_tool, target)
            self.loop.log(
                "FINDER_DECISION",
                direction=direction,
                target=target,
                tool=action,
                location=location,
            )

            if action == "report_found":
                if not location:
                    raise AgentLoopError("Gemma reported the target without a location")
                spoken = f"Your {target} is {location.rstrip('.')} .".replace(" .", ".")
                self._say(spoken)
                duration = time.monotonic() - started
                self.loop.log(
                    "FINDER_RESULT",
                    result="FOUND",
                    direction=direction,
                    target=target,
                    location=location,
                    duration_seconds=round(duration, 3),
                )
                return FinderResult(
                    True,
                    direction,
                    location,
                    tuple(gemma_moves),
                    duration,
                    str(self.loop.log_path),
                )
            if action == "report_not_found":
                if next_tool is not None:
                    raise AgentLoopError("Gemma stopped before checking every direction")
                spoken = (
                    ELDERLY_NOT_FOUND
                    if target.casefold() == "red umbrella"
                    else f"I couldn't find the {target} from here. Please check its usual place."
                )
                self._say(spoken)
                duration = time.monotonic() - started
                self.loop.log("FINDER_RESULT", result="NOT_FOUND", duration_seconds=round(duration, 3))
                return FinderResult(
                    False, None, spoken, tuple(gemma_moves), duration, str(self.loop.log_path)
                )
            if action != next_tool:
                raise AgentLoopError(f"Gemma chose {action}, expected systematic next tool {next_tool}")
            gemma_moves.append(action)
            self.loop.memory.tool_calls += 1
            self.loop.log("GEMMA_LOOK_DECISION", tool=action, issued_by="Gemma")
            direction_index += 1
            self._move_to(SEARCH_ORDER[direction_index], issued_by_gemma=True)

        raise AgentLoopError("finder exhausted its bounded search unexpectedly")

    def evaluate_negative_fixture(
        self,
        fixture_path: str | Path,
        *,
        target: str = "wearable eyeglasses",
    ) -> FinderResult:
        started = time.monotonic()
        fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        frames = fixture.get("frames") or {}
        if tuple(frames) != SEARCH_ORDER:
            raise AgentLoopError("negative fixture must contain center,left,right,up,down in order")

        moves: list[str] = []
        for index, direction in enumerate(SEARCH_ORDER):
            image_path = str(frames[direction])
            if not Path(image_path).is_file():
                raise AgentLoopError(f"negative fixture image missing: {image_path}")
            self.loop.memory.remember(direction, image_path, "negative fixture inspected")
            next_tool = (
                LOOK_FOR_DIRECTION[SEARCH_ORDER[index + 1]]
                if index + 1 < len(SEARCH_ORDER)
                else None
            )
            action, location = self._inspect(image_path, direction, next_tool, target)
            if action == "report_found":
                raise AgentLoopError(
                    f"negative fixture unexpectedly reported {target} in {direction}: {location}"
                )
            if action == "report_not_found":
                if next_tool is not None:
                    raise AgentLoopError("negative fixture stopped before all five directions")
                duration = time.monotonic() - started
                spoken = (
                    ELDERLY_NOT_FOUND
                    if target.casefold() == "red umbrella"
                    else f"I couldn't find the {target} from here. Please check its usual place."
                )
                self._say(spoken)
                self.loop.log("FINDER_RESULT", result="NOT_FOUND", fixture=str(fixture_path))
                return FinderResult(False, None, spoken, tuple(moves), duration, str(self.loop.log_path))
            if action != next_tool:
                raise AgentLoopError(f"negative fixture action {action} did not continue systematically")
            moves.append(action)

        raise AgentLoopError("negative fixture did not produce an honest not-found result")


def capture_negative_fixture(
    path: str | Path,
    *,
    target: str = "wearable eyeglasses",
    log_dir: str | Path | None = None,
) -> dict:
    finder = ElderlyFinder(speech=False, log_dir=log_dir)
    frames: dict[str, str] = {}
    for index, direction in enumerate(SEARCH_ORDER):
        finder._move_to(direction, issued_by_gemma=False)
        image_path = finder.loop.observe(direction)
        frames[direction] = image_path
        next_tool = (
            LOOK_FOR_DIRECTION[SEARCH_ORDER[index + 1]]
            if index + 1 < len(SEARCH_ORDER)
            else None
        )
        action, location = finder._inspect(image_path, direction, next_tool, target)
        if action == "report_found":
            raise AgentLoopError(
                f"cannot prepare negative fixture: Gemma found {target} in {direction}: {location}"
            )
    finder._move_to("center", issued_by_gemma=False)
    payload = {"target": target, "frames": frames, "source": "live Jetson camera sweep"}
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
