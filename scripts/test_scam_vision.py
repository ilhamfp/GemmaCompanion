#!/usr/bin/env python3
"""Verify that Gemma reads a visible SMS fixture and gives cautious scam advice."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.gemma import GemmaClient  # noqa: E402
from demos.companion import CONVERSATION_PROMPT, VISUAL_QUESTION_PROMPT  # noqa: E402


def _fixture(path: Path) -> None:
    image = Image.new("RGB", (1024, 576), "#f3f4f6")
    draw = ImageDraw.Draw(image)
    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    body = ImageFont.truetype(font_path, 38)
    title = ImageFont.truetype(bold_path, 46)
    draw.rounded_rectangle((90, 35, 934, 541), radius=40, fill="white", outline="#111827", width=6)
    draw.text((145, 90), "URGENT SECURITY ALERT", font=title, fill="#b91c1c")
    lines = (
        "Your bank account is locked.",
        "Verify now: bit.ly/bank-fix",
        "Reply with your one-time passcode.",
    )
    for index, line in enumerate(lines):
        draw.text((145, 190 + index * 85), line, font=body, fill="#111827")
    image.save(path)


def main() -> int:
    subprocess.run([str(REPO_ROOT / "scripts" / "ensure_gemma.sh")], check=True)
    with tempfile.TemporaryDirectory(prefix="gemma-scam-vision-") as directory:
        image_path = Path(directory) / "sms.png"
        _fixture(image_path)
        client = GemmaClient()
        started = time.monotonic()
        response, _ = client.step(
            [
                {"role": "system", "content": CONVERSATION_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "User's question: Is this a scam or not?\n"
                        f"{VISUAL_QUESTION_PROMPT}"
                    ),
                },
            ],
            [str(image_path)],
        )
        latency = time.monotonic() - started

    lower = response.casefold()
    if not any(word in lower for word in ("scam", "suspicious", "warning", "red flag")):
        raise AssertionError(f"response did not assess scam risk: {response!r}")
    if not any(word in lower for word in ("passcode", "link", "urgent", "verify")):
        raise AssertionError(f"response did not ground a visible warning sign: {response!r}")
    if not any(
        phrase in lower
        for phrase in ("do not", "don't", "should not", "shouldn't", "avoid", "never")
    ):
        raise AssertionError(f"response did not give cautious advice: {response!r}")
    if latency >= 5:
        raise AssertionError(f"scam visual answer took {latency:.3f}s")

    print("fixture_text: URGENT; bank locked; shortened link; one-time passcode request")
    print(f"gemma_response: {response}")
    print(f"latency_seconds: {latency:.3f}; limit: <5.000")
    print("advice: PASS; grounded warning signs and cautious next step")
    print("result: PASS Gemma read and assessed a visible scam SMS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
