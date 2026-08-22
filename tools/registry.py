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
    _schema("look_left", "Physically turn the camera left to inspect a new area."),
    _schema("look_right", "Physically turn the camera right to inspect a new area."),
    _schema("look_up", "Physically tilt the camera upward to inspect a new area."),
    _schema("look_down", "Physically tilt the camera downward to inspect a new area."),
    _schema("look_center", "Physically return the camera to its centered home position."),
]

HORIZONTAL_LOOK_SCHEMAS = LOOK_SCHEMAS[:2]

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
