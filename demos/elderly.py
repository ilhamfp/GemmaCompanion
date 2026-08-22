"""Voice-first, safety-bounded misplaced-object finder."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

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
    # Room-calibrated initial view faces forward and above the tabletop;
    # the autonomous left/tabletop sweep reveals the requested device.
    "center": (0.0, 25.0),
    "left": (-120.0, -25.0),
    "right": (120.0, -25.0),
    "up": (0.0, 25.0),
    "down": (0.0, -25.0),
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

    def _move_to(self, direction: str, *, issued_by_gemma: bool) -> tuple[float, float]:
        pan, tilt = SEARCH_POSITIONS[direction]
        started = time.monotonic()
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
        return position

    @staticmethod
    def _argument(call: dict, key: str) -> str:
        arguments = (call.get("function") or {}).get("arguments") or {}
        return " ".join(str(arguments.get(key) or "").split())

    def _inspect(
        self,
        image_path: str,
        direction: str,
        next_tool: str | None,
        target: str,
    ) -> tuple[str, str]:
        checked = ", ".join(
            item.direction for item in self.loop.memory.observations
        ) or "none"
        if next_tool:
            continuation = f"If the requested object is not clearly visible, call {next_tool} to continue the systematic search."
            tools = [REPORT_FOUND_SCHEMA, look_schema(next_tool)]
        else:
            continuation = "This is the final direction. If the requested object is not clearly visible, call report_not_found."
            tools = [REPORT_FOUND_SCHEMA, REPORT_NOT_FOUND_SCHEMA]
        vision_prompt = f"""Inspect only this fresh image for the user's {target}.
Current physical camera direction: {direction}.
Pay attention to the target's stated color, brand, shape, and object type.
Do not substitute a merely similar object or infer one outside the frame.
Brand text may be unreadable, so describe any candidate matching the target's physical appearance and type.
In one grounded sentence, state what matching candidate is visible and locate it relative to a table, chair, laptop, cable, or other physical object.
Never use image-relative wording such as left side or right side. If nothing matches, state that no matching object is visible."""
        visual_evidence, _ = self.loop._step(
            [
                {"role": "system", "content": f"{AGENT_CORE}\n\n{ELDERLY_PROMPT}"},
                {"role": "user", "content": vision_prompt},
            ],
            [image_path],
        )
        self.loop.log(
            "VISUAL_EVIDENCE",
            direction=direction,
            target=target,
            text=visual_evidence,
        )

        decision_prompt = f"""Request: find the user's {target}.
Current direction: {direction}. Previously inspected: {checked}.
Grounded evidence from your just-completed image inspection: {visual_evidence}
Report the requested object only if that evidence clearly describes a candidate matching its physical appearance and type.
If found, call report_found with one simple physical location naming nearby furniture or objects; never say a side of the image.
{continuation}
Call exactly one supplied tool and do not invent a location."""
        model_text, calls = self.loop._step(
            [
                {"role": "system", "content": f"{AGENT_CORE}\n\n{ELDERLY_PROMPT}"},
                {"role": "user", "content": decision_prompt},
            ],
            tools=tools,
        )
        if calls:
            call = calls[0]
            action = tool_name(call)
            location = self._argument(call, "location")
            physical_anchors = ("table", "desk", "chair", "laptop", "cable", "cup", "bag")
            if action == "report_found" and (
                "image" in location.lower()
                or not any(anchor in location.lower() for anchor in physical_anchors)
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
                                f"Original location wording: {location}. Reply with only a short physical "
                                "location using a table, chair, laptop, cable, or another nearby object. "
                                "Never mention the image or camera."
                            ),
                        },
                    ]
                )
                location = " ".join(refined.split()).rstrip(".")
                if "surface" in location.lower():
                    location = re.sub(r"\bsurface\b", "tabletop", location, flags=re.IGNORECASE)
            if action == "report_found" and "surface" in location.lower():
                location = re.sub(r"\bsurface\b", "tabletop", location, flags=re.IGNORECASE)
            return action, location

        match = re.match(r"^FOUND:\s*(.+)$", model_text, flags=re.IGNORECASE)
        if match:
            self.loop.log("PARSED_TEXT_ACTION", tool="report_found", text=model_text)
            return "report_found", match.group(1).strip()
        if model_text.upper().startswith("NOT_FOUND"):
            fallback_action = next_tool or "report_not_found"
            self.loop.log("PARSED_TEXT_ACTION", tool=fallback_action, text=model_text)
            return fallback_action, ""
        plain_action = model_text.strip().lower().strip("` .")
        if plain_action == next_tool or (next_tool is None and plain_action == "report_not_found"):
            self.loop.log("PARSED_TEXT_ACTION", tool=plain_action, text=model_text)
            return plain_action, ""
        raise AgentLoopError(f"Gemma returned no parseable finder action: {model_text!r}")

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
            image_path = self.loop.observe(direction)
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
