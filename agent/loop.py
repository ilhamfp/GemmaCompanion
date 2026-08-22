"""Bounded observe-think-act loop shared by both Gemma Companion demos."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat

from agent.gemma import GemmaClient
from agent.memory import SessionMemory
from agent.prompts import AGENT_CORE, INVENTORY_PROMPT
from camera.capture import CameraCaptureError, capture_image
from camera.obsbot import look_center
from tools.registry import HORIZONTAL_LOOK_SCHEMAS, dispatch_look, tool_name

MAX_TOOL_CALLS = 8
MAX_QUESTIONS = 12
MIN_AVAILABLE_BYTES = 500 * 1024 * 1024


class AgentLoopError(RuntimeError):
    """Raised when a bounded perception session cannot continue safely."""


def available_memory_bytes() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise AgentLoopError("MemAvailable is missing from /proc/meminfo")


class AgentLoop:
    def __init__(
        self,
        *,
        gemma: GemmaClient | None = None,
        log_dir: str | os.PathLike[str] | None = None,
        max_tool_calls: int = MAX_TOOL_CALLS,
        max_questions: int = MAX_QUESTIONS,
    ) -> None:
        self.gemma = gemma or GemmaClient()
        self.max_tool_calls = max_tool_calls
        self.max_questions = max_questions
        self.memory = SessionMemory()
        destination = Path(log_dir or Path.cwd() / "logs").expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.log_path = destination / f"session-{stamp}.jsonl"

    def log(self, action: str, **fields: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            **fields,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _step(self, messages: list[dict], images: list[str] | None = None, tools: list[dict] | None = None):
        before = available_memory_bytes()
        if before < MIN_AVAILABLE_BYTES:
            raise AgentLoopError(f"UNSAFE: only {before} bytes available before inference")
        text, tool_calls = self.gemma.step(messages, images, tools)
        after = available_memory_bytes()
        if after < MIN_AVAILABLE_BYTES:
            raise AgentLoopError(f"UNSAFE: only {after} bytes available after inference")
        self.log(
            "MODEL_STEP",
            latency_seconds=round(self.gemma.last_latency_seconds, 3),
            text=text,
            tool_calls=tool_calls,
            available_memory_bytes=after,
        )
        return text, tool_calls

    def observe(self, direction: str) -> str:
        started = time.monotonic()
        image_path = ""
        for attempt in range(1, 4):
            try:
                image_path = capture_image(Path.cwd() / "captures" / "sessions")
                break
            except CameraCaptureError as exc:
                self.log("CAPTURE_RETRY", direction=direction, attempt=attempt, error=str(exc))
                if attempt == 3:
                    raise
                time.sleep(0.25)
        self.log(
            "OBSERVE",
            direction=direction,
            image_path=image_path,
            latency_seconds=round(time.monotonic() - started, 3),
        )
        return image_path

    def inventory_frame(self, direction: str, image_path: str) -> str:
        text, _ = self._step(
            [
                {"role": "system", "content": AGENT_CORE},
                {"role": "user", "content": INVENTORY_PROMPT},
            ],
            [image_path],
        )
        if not text:
            raise AgentLoopError("Gemma returned an empty inventory")
        self.memory.remember(direction, image_path, text)
        self.log("MEMORY", direction=direction, inventory=text)
        return text

    def room_scan(self) -> str:
        """Perform the fixed left-center-right scan used at the start of both demos."""

        for direction, tool in (
            ("left", "look_left"),
            ("center", "look_center"),
            ("right", "look_right"),
        ):
            position = dispatch_look(tool)
            self.log(
                "ROOM_SCAN_MOVE",
                direction=direction,
                pan_degrees=position[0],
                tilt_degrees=position[1],
            )
            image_path = self.observe(direction)
            self.inventory_frame(direction, image_path)
        look_center()
        self.log("ROOM_SCAN_COMPLETE", inventory=self.memory.inventory())
        return self.memory.inventory()

    def choose_horizontal_look(self) -> str:
        if self.memory.tool_calls >= self.max_tool_calls:
            raise AgentLoopError("tool-call bound reached")
        prompt = f"""Current visual memory:
{self.memory.inventory()}

Objective: discover one additional concrete room object that the current camera view cannot show.
The evidence is insufficient. Independently choose one horizontal camera direction and call exactly one look tool now.
Do not ask the human and do not merely describe what you would do."""
        text, calls = self._step(
            [
                {"role": "system", "content": AGENT_CORE},
                {"role": "user", "content": prompt},
            ],
            tools=HORIZONTAL_LOOK_SCHEMAS,
        )
        if calls:
            name = tool_name(calls[0])
        else:
            name = text.strip().lower().strip("` .")
            if name not in {"look_left", "look_right"}:
                raise AgentLoopError("Gemma did not issue a look tool call")
            self.log("PARSED_TEXT_ACTION", tool=name, text=text)
        if name not in {"look_left", "look_right"}:
            raise AgentLoopError(f"Gemma issued an unexpected tool: {name}")
        self.memory.tool_calls += 1
        self.log("GEMMA_LOOK_DECISION", tool=name, issued_by="Gemma")
        return name

    def execute_look(self, name: str) -> tuple[str, tuple[float, float]]:
        started = time.monotonic()
        position = dispatch_look(name)
        self.log(
            "LOOK",
            tool=name,
            pan_degrees=position[0],
            tilt_degrees=position[1],
            latency_seconds=round(time.monotonic() - started, 3),
        )
        return self.observe(name.removeprefix("look_")), position

    def integrate_new_frame(self, direction: str, image_path: str, previous_inventory: str) -> str:
        prompt = f"""Previous view inventory:
{previous_inventory}

This is a fresh frame captured only after your camera moved {direction}.
Name one concrete object visible now that was absent from the previous inventory.
Reply exactly as NEW_OBJECT: followed by the object and a short location phrase."""
        text, _ = self._step(
            [
                {"role": "system", "content": AGENT_CORE},
                {"role": "user", "content": prompt},
            ],
            [image_path],
        )
        if not re.match(r"^NEW_OBJECT:\s*\S+", text, flags=re.IGNORECASE):
            raise AgentLoopError(f"post-look message is not parseable: {text!r}")
        object_phrase = text.split(":", 1)[1].strip().lower()
        object_words = set(re.findall(r"[a-z]+", object_phrase))
        prior_words = set(re.findall(r"[a-z]+", previous_inventory.lower()))
        useful_words = object_words - {"a", "an", "the", "is", "on", "in", "at", "near", "beside", "to", "of"}
        if useful_words and useful_words <= prior_words:
            raise AgentLoopError(f"post-look object was already in prior inventory: {text!r}")
        self.memory.remember(direction, image_path, text)
        self.log("POST_LOOK_REFERENCE", direction=direction, text=text, new_only=True)
        return text

    @staticmethod
    def frame_difference(first_path: str, second_path: str) -> float:
        with Image.open(first_path) as first, Image.open(second_path) as second:
            first_rgb = first.convert("RGB")
            second_rgb = second.convert("RGB").resize(first_rgb.size)
            difference = ImageChops.difference(first_rgb, second_rgb)
            return sum(ImageStat.Stat(difference).mean) / 3

    def run_scripted_look_scenario(self) -> dict[str, Any]:
        look_center()
        time.sleep(0.8)
        try:
            initial_path = self.observe("center")
            initial_inventory = self.inventory_frame("center", initial_path)
            look_tool = self.choose_horizontal_look()
            new_path, position = self.execute_look(look_tool)
            difference = self.frame_difference(initial_path, new_path)
            if difference < 8.0:
                raise AgentLoopError(f"physical frames differ by only {difference:.3f}")
            post_message = self.integrate_new_frame(
                look_tool.removeprefix("look_"), new_path, initial_inventory
            )
            self.log("SESSION_RESULT", result="PASS", physical_frame_diff=round(difference, 3))
            return {
                "look_tool": look_tool,
                "position": position,
                "initial_inventory": initial_inventory,
                "post_message": post_message,
                "frame_difference": difference,
                "log_path": str(self.log_path),
            }
        finally:
            look_center()
