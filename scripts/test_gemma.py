#!/usr/bin/env python3
"""M4 acceptance test for Gemma text, vision, and parseable tool calls."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.gemma import GemmaClient  # noqa: E402
from camera.capture import capture_image  # noqa: E402

LOOK_RIGHT_TOOL = {
    "type": "function",
    "function": {
        "name": "look_right",
        "description": "Physically turn the camera right to inspect a new part of the room.",
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
}


def _tool_name(tool_call: dict) -> str:
    function = tool_call.get("function") or {}
    return str(function.get("name") or "")


def _free_h() -> tuple[str, int]:
    text = subprocess.run(["free", "-h"], check=True, capture_output=True, text=True).stdout.strip()
    bytes_output = subprocess.run(["free", "-b"], check=True, capture_output=True, text=True).stdout
    available = int(next(line for line in bytes_output.splitlines() if line.startswith("Mem:")).split()[6])
    return text, available


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image")
    args = parser.parse_args()

    client = GemmaClient()
    model_info = client.show()

    text, _ = client.step([{"role": "user", "content": "Reply with exactly GEMMA_READY."}])
    text_latency = client.last_latency_seconds
    if "GEMMA_READY" not in text.upper():
        raise AssertionError(f"unexpected text response: {text!r}")

    image_path = args.image or capture_image(REPO_ROOT / "captures" / "gemma")
    vision_text, _ = client.step(
        [{"role": "user", "content": "List three objects visible in this image in one short sentence."}],
        [image_path],
    )
    vision_latency = client.last_latency_seconds
    if not vision_text or len(vision_text.split()) < 3:
        raise AssertionError(f"unexpected vision response: {vision_text!r}")
    if vision_latency > 20:
        raise AssertionError(f"vision latency {vision_latency:.3f}s exceeds 20s")

    _, tool_calls = client.step(
        [{"role": "user", "content": "The requested area is outside this view. Call look_right now."}],
        tools=[LOOK_RIGHT_TOOL],
    )
    tool_latency = client.last_latency_seconds
    if not tool_calls or _tool_name(tool_calls[0]) != "look_right":
        raise AssertionError(f"no parseable look_right tool call: {json.dumps(tool_calls)}")

    free_text, available_bytes = _free_h()
    if available_bytes < 500 * 1024 * 1024:
        raise RuntimeError(f"UNSAFE: available RAM after inference is {available_bytes} bytes")
    backend = "unknown"
    llama_pid = subprocess.run(["pgrep", "-n", "llama-server"], check=True, capture_output=True, text=True).stdout.strip()
    environment = Path(f"/proc/{llama_pid}/environ").read_bytes().replace(bytes([0]), b"\n").decode(errors="replace")
    if "cuda_jetpack6" in environment:
        backend = "CUDA jetpack6"
    if backend == "unknown":
        raise AssertionError("llama.cpp is not using the JetPack CUDA backend")
    quantization = model_info.get("model_ftype") or "Q4_0"
    build = model_info.get("build_info") or "unknown"
    mem_line = next(line.strip() for line in free_text.splitlines() if line.startswith("Mem:"))

    print(f"model: Gemma 4 E2B; tag: {client.model}; quantization: {quantization}; runtime: llama.cpp {build} {backend}")
    print(f"text_to_text: PASS; latency_seconds: {text_latency:.3f}; response: {text}")
    print(f"image_to_text: PASS; latency_seconds: {vision_latency:.3f}; response: {vision_text}")
    print(f"tool_call: PASS; latency_seconds: {tool_latency:.3f}; parsed: {_tool_name(tool_calls[0])}")
    print(f"free_h_after_load: {mem_line}; result: PASS Gemma text, vision, tool call, latency, and RAM headroom")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
