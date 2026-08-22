"""Voice-first, safety-bounded misplaced-glasses finder."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from agent.loop import AgentLoop, AgentLoopError
from agent.prompts import AGENT_CORE, ELDERLY_PROMPT
from audio.tts import speak
from tools.registry import (
    REPORT_FOUND_SCHEMA,
    REPORT_NOT_FOUND_SCHEMA,
    dispatch_look,
    look_schema,
    tool_name,
)

SEARCH_ORDER = ("center", "left", "right", "up", "down")
LOOK_FOR_DIRECTION = {direction: f"look_{direction}" for direction in SEARCH_ORDER}
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


def is_medical_request(text: str) -> bool:
    return bool(set(re.findall(r"[a-z]+", text.lower())) & MEDICAL_WORDS)


def medical_refusal() -> str:
    return "I can't help with medical advice; please ask a caregiver or doctor."


@dataclass(frozen=True)
class FinderResult:
    found: bool
    direction: str | None
    location: str
    gemma_moves: tuple[str, ...]
    duration_seconds: float
    log_path: str


class ElderlyFinder:
    def __init__(self, *, speech: bool = True, log_dir: str | Path | None = None) -> None:
        self.speech = speech
        self.loop = AgentLoop(log_dir=log_dir)

    def _say(self, text: str) -> None:
        clean = " ".join(text.split())
        print(f"Gemma: {clean}", flush=True)
        self.loop.log("SAY", text=clean)
        if self.speech:
            speak(clean, words_per_minute=120)

    @staticmethod
    def _argument(call: dict, key: str) -> str:
        arguments = (call.get("function") or {}).get("arguments") or {}
        return " ".join(str(arguments.get(key) or "").split())

    def _inspect(self, image_path: str, direction: str, next_tool: str | None) -> tuple[str, str]:
        checked = ", ".join(
            item.direction for item in self.loop.memory.observations
        ) or "none"
        if next_tool:
            continuation = f"If glasses are not clearly visible, call {next_tool} to continue the systematic search."
            tools = [REPORT_FOUND_SCHEMA, look_schema(next_tool)]
        else:
            continuation = "This is the final direction. If glasses are not clearly visible, call report_not_found."
            tools = [REPORT_FOUND_SCHEMA, REPORT_NOT_FOUND_SCHEMA]
        prompt = f"""Request: find the user's wearable eyeglasses.
Current physical camera direction: {direction}.
Previously inspected directions: {checked}.
Inspect only this fresh image. Report glasses only when their frame or lenses are clearly visible.
Do not mistake laptops, screens, cables, bags, or faces without visible frames for glasses.
If found, call report_found with one simple furniture-relative location.
{continuation}
Call exactly one supplied tool and do not invent a location."""
        model_text, calls = self.loop._step(
            [
                {"role": "system", "content": f"{AGENT_CORE}\n\n{ELDERLY_PROMPT}"},
                {"role": "user", "content": prompt},
            ],
            [image_path],
            tools,
        )
        if calls:
            call = calls[0]
            return tool_name(call), self._argument(call, "location")

        match = re.match(r"^FOUND:\s*(.+)$", model_text, flags=re.IGNORECASE)
        if match:
            self.loop.log("PARSED_TEXT_ACTION", tool="report_found", text=model_text)
            return "report_found", match.group(1).strip()
        if model_text.upper().startswith("NOT_FOUND"):
            fallback_action = next_tool or "report_not_found"
            self.loop.log("PARSED_TEXT_ACTION", tool=fallback_action, text=model_text)
            return fallback_action, ""
        raise AgentLoopError(f"Gemma returned no parseable finder action: {model_text!r}")

    def search_live(self, request: str = "Please find my glasses") -> FinderResult:
        if is_medical_request(request):
            refusal = medical_refusal()
            self._say(refusal)
            self.loop.log("SAFETY_REFUSAL", request=request, response=refusal)
            return FinderResult(False, None, refusal, (), 0.0, str(self.loop.log_path))

        started = time.monotonic()
        self._say("You want me to find your glasses, is that right?")
        self.loop.log("FINDER_START", request=request)
        gemma_moves: list[str] = []

        dispatch_look("look_center")
        direction_index = 0
        while direction_index < len(SEARCH_ORDER):
            direction = SEARCH_ORDER[direction_index]
            image_path = self.loop.observe(direction)
            self.loop.memory.remember(direction, image_path, "inspected for glasses")
            next_tool = (
                LOOK_FOR_DIRECTION[SEARCH_ORDER[direction_index + 1]]
                if direction_index + 1 < len(SEARCH_ORDER)
                else None
            )
            action, location = self._inspect(image_path, direction, next_tool)
            self.loop.log("FINDER_DECISION", direction=direction, tool=action, location=location)

            if action == "report_found":
                if not location:
                    raise AgentLoopError("Gemma reported glasses without a location")
                spoken = f"Your glasses are {location.rstrip('.')} .".replace(" .", ".")
                self._say(spoken)
                duration = time.monotonic() - started
                self.loop.log(
                    "FINDER_RESULT",
                    result="FOUND",
                    direction=direction,
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
                spoken = "I couldn't find your glasses from here; please check their usual case."
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
            dispatch_look(action)
            direction_index += 1

        raise AgentLoopError("finder exhausted its bounded search unexpectedly")

    def evaluate_negative_fixture(self, fixture_path: str | Path) -> FinderResult:
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
            action, location = self._inspect(image_path, direction, next_tool)
            if action == "report_found":
                raise AgentLoopError(
                    f"negative fixture unexpectedly reported glasses in {direction}: {location}"
                )
            if action == "report_not_found":
                if next_tool is not None:
                    raise AgentLoopError("negative fixture stopped before all five directions")
                duration = time.monotonic() - started
                spoken = "I couldn't find your glasses from here; please check their usual case."
                self._say(spoken)
                self.loop.log("FINDER_RESULT", result="NOT_FOUND", fixture=str(fixture_path))
                return FinderResult(False, None, spoken, tuple(moves), duration, str(self.loop.log_path))
            if action != next_tool:
                raise AgentLoopError(f"negative fixture action {action} did not continue systematically")
            moves.append(action)

        raise AgentLoopError("negative fixture did not produce an honest not-found result")


def capture_negative_fixture(path: str | Path, *, log_dir: str | Path | None = None) -> dict:
    finder = ElderlyFinder(speech=False, log_dir=log_dir)
    frames: dict[str, str] = {}
    for index, direction in enumerate(SEARCH_ORDER):
        tool = LOOK_FOR_DIRECTION[direction]
        dispatch_look(tool)
        image_path = finder.loop.observe(direction)
        frames[direction] = image_path
        next_tool = (
            LOOK_FOR_DIRECTION[SEARCH_ORDER[index + 1]]
            if index + 1 < len(SEARCH_ORDER)
            else None
        )
        action, location = finder._inspect(image_path, direction, next_tool)
        if action == "report_found":
            raise AgentLoopError(
                f"cannot prepare absent-glasses fixture: Gemma found glasses in {direction}: {location}"
            )
    dispatch_look("look_center")
    payload = {"target": "glasses", "frames": frames, "source": "live Jetson camera sweep"}
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload
