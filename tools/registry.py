"""Tool schemas and deterministic dispatch for physical companion actions."""

from __future__ import annotations

import time
from typing import Callable

from camera.obsbot import look_center, look_down, look_left, look_right, look_up

LOOK_FUNCTIONS: dict[str, Callable[[], tuple[float, float]]] = {
    "look_left": look_left,
    "look_right": look_right,
    "look_up": look_up,
    "look_down": look_down,
    "look_center": look_center,
}


def _schema(name: str, description: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    }


LOOK_SCHEMAS = [
    _schema("look_left", "Execute a physical camera turn toward the user's left-hand side."),
    _schema("look_right", "Execute a physical camera turn toward the user's right-hand side."),
    _schema("look_up", "Execute a physical camera tilt toward a higher or overhead area."),
    _schema("look_down", "Execute a physical camera tilt toward a lower or floor area."),
    _schema("look_center", "Execute a physical return to the neutral forward-facing home position."),
]

HORIZONTAL_LOOK_SCHEMAS = LOOK_SCHEMAS[:2]

STOP_SPEAKING_SCHEMA = _schema(
    "cancel_current_response",
    "Confirm that the current spoken response or physical task should stop. Voice onset already "
    "interrupts playback immediately; use this tool when the user's new request is cancellation.",
)

SLEEP_SCHEMA = _schema(
    "sleep",
    "Enter a quiet idle state until the user's next detected utterance resumes interaction.",
)

MAKE_VOICE_LOUDER_SCHEMA = _schema(
    "make_voice_louder",
    "Physically raise the audible USB speaker volume by one safe step.",
)

MAKE_VOICE_SOFTER_SCHEMA = _schema(
    "make_voice_softer",
    "Physically lower the audible USB speaker volume by one safe step.",
)

SET_VOLUME_SCHEMA = {
    "type": "function",
    "function": {
        "name": "set_volume",
        "description": "Set the physical USB speaker playback volume to an exact percentage.",
        "parameters": {
            "type": "object",
            "properties": {
                "percent": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "description": "Requested playback volume from zero through one hundred.",
                }
            },
            "required": ["percent"],
            "additionalProperties": False,
        },
    },
}

FIND_OBJECT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "find_object",
        "description": (
            "Start a systematic physical camera search when the user asks you to find, "
            "locate, or look for a misplaced everyday object."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": (
                        "A concise visual description expanded beyond only a product name. "
                        "Include common shape, color, and object type when known, such as "
                        "small white Apple AirPods wireless-earbud charging case."
                    ),
                }
            },
            "required": ["target"],
            "additionalProperties": False,
        },
    },
}

INSPECT_VIEW_SCHEMA = {
    "type": "function",
    "function": {
        "name": "inspect_view",
        "description": (
            "Capture and inspect a fresh camera frame before answering a question about something "
            "currently visible. Use this whenever the user refers to this or that object, something "
            "they are holding or showing, a visible color or identity, or writing on a label or screen."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
}

RESPOND_NORMALLY_SCHEMA = _schema(
    "respond_normally",
    "Answer from language knowledge and conversation only when no physical action, current camera "
    "evidence, object search, or device setting is needed.",
)

FINISH_MOVEMENT_SCHEMA = _schema(
    "finish_movement",
    "The completed camera movement fully satisfies the original request; no camera-derived answer remains.",
)

MOVEMENT_COMPLETION_SCHEMAS = [INSPECT_VIEW_SCHEMA, FINISH_MOVEMENT_SCHEMA]

COMPANION_TOOL_SCHEMAS = [
    *LOOK_SCHEMAS,
    INSPECT_VIEW_SCHEMA,
    FIND_OBJECT_SCHEMA,
    MAKE_VOICE_LOUDER_SCHEMA,
    MAKE_VOICE_SOFTER_SCHEMA,
    SET_VOLUME_SCHEMA,
    STOP_SPEAKING_SCHEMA,
    SLEEP_SCHEMA,
]

COMPANION_DECISION_SCHEMAS = [*COMPANION_TOOL_SCHEMAS, RESPOND_NORMALLY_SCHEMA]

ASK_USER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "ask_user",
        "description": "Ask the user exactly one concise yes/no question about their object.",
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
            "additionalProperties": False,
        },
    },
}

FINAL_ANSWER_SCHEMA = {
    "type": "function",
    "function": {
        "name": "final_answer",
        "description": "Make one evidence-based guess for the user's object.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
    },
}

AKINATOR_ACTION_SCHEMAS = [ASK_USER_SCHEMA, FINAL_ANSWER_SCHEMA]

REPORT_FOUND_SCHEMA = {
    "type": "function",
    "function": {
        "name": "report_found",
        "description": "Report the clearly visible requested object with a plain furniture-relative location.",
        "parameters": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
            "additionalProperties": False,
        },
    },
}

REPORT_NOT_FOUND_SCHEMA = {
    "type": "function",
    "function": {
        "name": "report_not_found",
        "description": "Honestly finish after every search direction has been inspected without seeing the requested object.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
}


def look_schema(name: str) -> dict:
    return next(schema for schema in LOOK_SCHEMAS if schema["function"]["name"] == name)


def tool_name(tool_call: dict) -> str:
    return str((tool_call.get("function") or {}).get("name") or "")


def dispatch_look(name: str, *, settle_seconds: float = 0.8) -> tuple[float, float]:
    if name not in LOOK_FUNCTIONS:
        raise ValueError(f"unsupported look tool: {name}")
    position = LOOK_FUNCTIONS[name]()
    time.sleep(settle_seconds)
    return position
