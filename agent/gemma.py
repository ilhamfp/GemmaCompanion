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

    def _request(self, route: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.endpoint}{route}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="GET" if body is None else "POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise GemmaError(f"llama.cpp request failed at {route}: {exc}") from exc

    def show(self) -> dict[str, Any]:
        """Return llama.cpp model/runtime properties."""

        return self._request("/props")

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
    def _fallback_tool_calls(text: str, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        allowed = {
            tool.get("function", {}).get("name")
            for tool in tools
            if tool.get("type") == "function"
        }
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
    ) -> tuple[str, list[dict[str, Any]]]:
        """Run one local Gemma turn and return text plus normalized tool calls."""

        if not messages:
            raise ValueError("messages must not be empty")
        request_messages = [dict(message) for message in messages]
        if images:
            target_index = next(
                (index for index in range(len(request_messages) - 1, -1, -1) if request_messages[index].get("role") == "user"),
                None,
            )
            if target_index is None:
                raise ValueError("images require at least one user message")
            text_content = str(request_messages[target_index].get("content") or "")
            request_messages[target_index]["content"] = [
                {"type": "text", "text": text_content},
                *[self._image_part(image) for image in images],
            ]

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": request_messages,
            "stream": False,
            "temperature": 0,
            "max_tokens": int(os.environ.get("GEMMA_MAX_TOKENS", "96")),
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        started = time.monotonic()
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
) -> tuple[str, list[dict[str, Any]]]:
    """PRD target API backed by one reusable local Gemma client."""

    global _default_client
    if _default_client is None:
        _default_client = GemmaClient()
    return _default_client.step(messages, images, tools)
