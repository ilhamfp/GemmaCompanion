"""Small OpenAI-compatible client for local Gemma 4 on llama.cpp."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "gemma4:e2b-it-qat"
DEFAULT_ENDPOINT = "http://127.0.0.1:11434"


class GemmaError(RuntimeError):
    """Raised when the local Gemma runtime cannot answer safely."""


class GemmaClient:
    def __init__(self, model: str | None = None, endpoint: str | None = None) -> None:
        self.model = model or os.environ.get("GEMMA_MODEL", DEFAULT_MODEL)
        self.endpoint = (endpoint or os.environ.get("LLAMA_ENDPOINT", DEFAULT_ENDPOINT)).rstrip("/")
        self.last_response: dict[str, Any] = {}
        self.last_latency_seconds = 0.0

    @property
    def last_finish_reason(self) -> str:
        """Return the completion reason for the most recent model step."""

        choices = self.last_response.get("choices") or []
        if not choices:
            return ""
        return str(choices[0].get("finish_reason") or "")

    def _request(self, route: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.endpoint}{route}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="GET" if body is None else "POST",
        )
        try:
            timeout_seconds = float(os.environ.get("GEMMA_REQUEST_TIMEOUT_SECONDS", "30"))
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise GemmaError(f"llama.cpp request failed at {route}: {exc}") from exc

    def show(self) -> dict[str, Any]:
        """Return llama.cpp model/runtime properties."""

        return self._request("/props")

    def health(self) -> dict[str, Any]:
        """Return lightweight server health or raise when llama.cpp has exited."""

        return self._request("/health")

    @staticmethod
    def _image_part(image: str | os.PathLike[str]) -> dict[str, Any]:
        path = Path(image).expanduser().resolve()
        if not path.is_file():
            raise GemmaError(f"image does not exist: {path}")
        mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
        }

    @staticmethod
    def _audio_part(audio: str | os.PathLike[str]) -> dict[str, Any]:
        path = Path(audio).expanduser().resolve()
        if not path.is_file():
            raise GemmaError(f"audio does not exist: {path}")
        suffix = path.suffix.casefold()
        if suffix not in {".wav", ".mp3"}:
            raise GemmaError(f"unsupported Gemma audio format: {path.suffix or '<none>'}")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return {
            "type": "input_audio",
            "input_audio": {"data": encoded, "format": suffix.removeprefix(".")},
        }

    @staticmethod
    def _attach_parts(
        messages: list[dict[str, Any]],
        *,
        images: list[str | os.PathLike[str]] | None,
        audios: list[str | os.PathLike[str]] | None,
    ) -> None:
        if not images and not audios:
            return
        target_index = next(
            (
                index
                for index in range(len(messages) - 1, -1, -1)
                if messages[index].get("role") == "user"
            ),
            None,
        )
        if target_index is None:
            raise ValueError("media requires at least one user message")
        existing = messages[target_index].get("content")
        if isinstance(existing, list):
            content = [dict(part) for part in existing]
        else:
            text = str(existing or "")
            content = [{"type": "text", "text": text}] if text else []
        content.extend(GemmaClient._audio_part(audio) for audio in audios or [])
        content.extend(GemmaClient._image_part(image) for image in images or [])
        messages[target_index]["content"] = content

    @staticmethod
    def _fallback_tool_calls(text: str, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        functions = {
            tool.get("function", {}).get("name"): tool.get("function", {})
            for tool in tools
            if tool.get("type") == "function" and tool.get("function", {}).get("name")
        }
        allowed = set(functions)
        bare = text.strip().strip("`\"'. ")
        if bare in allowed:
            return [{"function": {"name": bare, "arguments": {}}}]

        def parse_arguments(raw_arguments: str) -> dict[str, Any]:
            arguments: dict[str, Any] = {}
            for pair in re.finditer(
                r"([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*"
                r"(<\|\"\|>.*?<\|\"\|>|\"(?:\\.|[^\"])*\"|-?\d+(?:\.\d+)?|true|false)",
                raw_arguments,
                flags=re.DOTALL | re.IGNORECASE,
            ):
                key, raw = pair.groups()
                if raw.startswith('<|"|>') and raw.endswith('<|"|>'):
                    value: Any = raw[5:-5]
                elif raw.startswith('"'):
                    try:
                        value = json.loads(raw)
                    except json.JSONDecodeError:
                        value = raw.strip('"')
                elif raw.casefold() in {"true", "false"}:
                    value = raw.casefold() == "true"
                else:
                    value = float(raw) if "." in raw else int(raw)
                arguments[key] = value
            return arguments

        native_calls: list[dict[str, Any]] = []
        native_pattern = re.compile(
            r"(?:<\|tool_call>)?\s*(?:call\s*:?\s*)?([a-zA-Z_][a-zA-Z0-9_]*)\s*"
            r"\{(.*?)\}(?:<tool_call\|>)?",
            flags=re.DOTALL,
        )
        for match in native_pattern.finditer(text):
            name = match.group(1)
            if name not in allowed:
                continue
            native_calls.append(
                {
                    "function": {
                        "name": name,
                        "arguments": parse_arguments(match.group(2)),
                    }
                }
            )
        line_calls: list[dict[str, Any]] = []
        native_names = {call["function"]["name"] for call in native_calls}
        for line in text.splitlines():
            line_name = line.strip().strip("`\"'. ")
            if line_name in allowed and line_name not in native_names:
                line_calls.append({"function": {"name": line_name, "arguments": {}}})
                native_names.add(line_name)
        if native_calls or line_calls:
            return [*native_calls, *line_calls]
        positional_call = re.match(
            r"^\s*(?:call\s*:?\s*)?([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)",
            text,
            flags=re.DOTALL,
        )
        if positional_call and positional_call.group(1) in allowed:
            name, raw_value = positional_call.groups()
            required = functions[name].get("parameters", {}).get("required") or []
            arguments: dict[str, Any] = {}
            if len(required) == 1 and raw_value.strip():
                value_text = raw_value.strip()
                keyword_value = re.fullmatch(
                    rf"{re.escape(required[0])}\s*=\s*(.+)", value_text, flags=re.DOTALL
                )
                if keyword_value:
                    value_text = keyword_value.group(1).strip()
                if value_text.startswith(('"', "'")) and value_text.endswith(('"', "'")):
                    value: Any = value_text[1:-1]
                elif re.fullmatch(r"-?\d+", value_text):
                    value = int(value_text)
                elif re.fullmatch(r"-?\d+\.\d+", value_text):
                    value = float(value_text)
                elif value_text.casefold() in {"true", "false"}:
                    value = value_text.casefold() == "true"
                else:
                    value = value_text
                arguments[required[0]] = value
            return [{"function": {"name": name, "arguments": arguments}}]
        leading_name = re.match(
            r"^\s*(?:<\|tool_call>)?\s*(?:call\s*:?\s*)?"
            r"([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:[.\n]|$)",
            text,
        )
        if leading_name and leading_name.group(1) in allowed:
            return [{"function": {"name": leading_name.group(1), "arguments": {}}}]
        for candidate in re.findall(r"\{[^{}]+\}", text, flags=re.DOTALL):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            name = parsed.get("action") or parsed.get("name")
            if name in allowed:
                arguments = parsed.get("arguments") or {
                    key: value for key, value in parsed.items() if key not in {"action", "name"}
                }
                return [{"function": {"name": name, "arguments": arguments}}]
        return []

    @staticmethod
    def _normalize_tool_calls(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for tool_call in tool_calls:
            call = dict(tool_call)
            function = dict(call.get("function") or {})
            arguments = function.get("arguments")
            if isinstance(arguments, str):
                try:
                    function["arguments"] = json.loads(arguments)
                except json.JSONDecodeError:
                    function["arguments"] = {"raw": arguments}
            call["function"] = function
            normalized.append(call)
        return normalized

    def step(
        self,
        messages: list[dict[str, Any]],
        images: list[str | os.PathLike[str]] | None = None,
        tools: list[dict[str, Any]] | None = None,
        audios: list[str | os.PathLike[str]] | None = None,
        *,
        max_tokens: int | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Run one local Gemma turn and return text plus normalized tool calls."""

        if not messages:
            raise ValueError("messages must not be empty")
        request_messages = [dict(message) for message in messages]
        self._attach_parts(request_messages, images=images, audios=audios)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": request_messages,
            "stream": False,
            "temperature": 0,
            "max_tokens": (
                max_tokens
                if max_tokens is not None
                else int(os.environ.get("GEMMA_MAX_TOKENS", "64"))
            ),
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"

        started = time.monotonic()
        try:
            response = self._request("/v1/chat/completions", payload)
        except GemmaError as exc:
            if not tools or "HTTP Error 500" not in str(exc):
                raise
            payload["parse_tool_calls"] = False
            response = self._request("/v1/chat/completions", payload)
        self.last_latency_seconds = time.monotonic() - started
        self.last_response = response

        choices = response.get("choices") or []
        if not choices:
            raise GemmaError(f"llama.cpp returned no choices: {response}")
        message = choices[0].get("message") or {}
        text = str(message.get("content") or "").strip()
        tool_calls = self._normalize_tool_calls(message.get("tool_calls") or [])
        if tools and not tool_calls:
            tool_calls = self._fallback_tool_calls(text, tools)
        return text, tool_calls


_default_client: GemmaClient | None = None


def step(
    messages: list[dict[str, Any]],
    images: list[str | os.PathLike[str]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    audios: list[str | os.PathLike[str]] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """PRD target API backed by one reusable local Gemma client."""

    global _default_client
    if _default_client is None:
        _default_client = GemmaClient()
    return _default_client.step(messages, images, tools, audios)
