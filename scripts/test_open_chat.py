#!/usr/bin/env python3
"""Verify unfamiliar non-physical requests receive ordinary Gemma answers."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from demos.companion import CompanionSession  # noqa: E402

QUESTIONS = (
    "Why does metal usually feel colder than wood in the same room?",
    "Give me a two-sentence explanation of photosynthesis.",
    "What is a practical way to remember someone's name?",
    "If a train travels sixty kilometers in one hour, what is its average speed?",
    "Tell me a short joke about a robot.",
)


def main() -> int:
    session = CompanionSession(speech=False, microphone=False)
    try:
        for question in QUESTIONS:
            result = session.handle_text(question)
            if result.action != "chat" or not result.response or result.image_path:
                raise AssertionError(f"ordinary request was not ordinary chat: {question!r}; {result}")
            print(f"open_chat: PASS; question={question}; response={result.response}")
    finally:
        session.stop()
    print("result: PASS unfamiliar general requests receive normal Gemma answers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
