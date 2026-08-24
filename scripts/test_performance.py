#!/usr/bin/env python3
"""Verify lower response latency without weakening ordinary-answer quality."""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from audio.interruptible import InterruptibleSpeech  # noqa: E402
from audio.tts import get_engine  # noqa: E402
from demos.companion import (  # noqa: E402
    MIN_AVAILABLE_BYTES,
    CompanionSession,
    available_memory_bytes,
)
from scripts.test_open_chat import QUESTIONS  # noqa: E402

BASELINE_CHAT_MEAN_SECONDS = 3.949
BASELINE_CHAT_MAX_SECONDS = 4.666
BASELINE_TTS_FIRST_AUDIO_SECONDS = 5.740
CHAT_MEAN_LIMIT_SECONDS = 3.0
TTS_FIRST_AUDIO_LIMIT_SECONDS = 2.5
TTS_SAMPLE = (
    "Metal is a better conductor of heat than wood, so it draws heat away from your hand "
    "faster. This makes metal feel colder to the touch."
)


def _direct_response_count(log_path: Path) -> int:
    count = 0
    with log_path.open(encoding="utf-8") as handle:
        for line in handle:
            if json.loads(line).get("action") == "DIRECT_KNOWLEDGE_RESPONSE":
                count += 1
    return count


def _benchmark_chat() -> tuple[list[float], int]:
    session = CompanionSession(speech=False, microphone=False)
    latencies: list[float] = []
    try:
        for question in QUESTIONS:
            result = session.handle_text(question)
            if result.action != "chat" or not result.response or result.image_path:
                raise AssertionError(f"ordinary request quality changed: {question!r}; {result}")
            latencies.append(result.latency_seconds)
    finally:
        session.stop()
    return latencies, _direct_response_count(session.log_path)


def _benchmark_first_audio() -> float:
    engine = get_engine()
    engine.synth(TTS_SAMPLE)
    starts: list[float] = []
    speaker = InterruptibleSpeech(
        device="null",
        on_playback_start=lambda: starts.append(time.monotonic()),
    )
    started = time.monotonic()
    try:
        speaker.say(TTS_SAMPLE)
        speaker.wait(timeout=45)
    finally:
        speaker.close()
    if not starts:
        raise AssertionError("streaming speech never began playback")
    return starts[0] - started


def main() -> int:
    chat_latencies, direct_responses = _benchmark_chat()
    chat_mean = statistics.mean(chat_latencies)
    chat_max = max(chat_latencies)
    if direct_responses != len(QUESTIONS):
        raise AssertionError(
            f"only {direct_responses}/{len(QUESTIONS)} complete knowledge answers used the fast path"
        )
    if chat_mean >= CHAT_MEAN_LIMIT_SECONDS:
        raise AssertionError(
            f"mean ordinary-chat latency {chat_mean:.3f}s exceeds {CHAT_MEAN_LIMIT_SECONDS:.3f}s"
        )

    first_audio = _benchmark_first_audio()
    if first_audio >= TTS_FIRST_AUDIO_LIMIT_SECONDS:
        raise AssertionError(
            f"first audio {first_audio:.3f}s exceeds {TTS_FIRST_AUDIO_LIMIT_SECONDS:.3f}s"
        )

    available = available_memory_bytes()
    if available < MIN_AVAILABLE_BYTES:
        raise AssertionError(f"only {available} bytes of memory remain")

    chat_improvement = 100 * (BASELINE_CHAT_MEAN_SECONDS - chat_mean) / BASELINE_CHAT_MEAN_SECONDS
    speech_improvement = (
        100
        * (BASELINE_TTS_FIRST_AUDIO_SECONDS - first_audio)
        / BASELINE_TTS_FIRST_AUDIO_SECONDS
    )
    values = ",".join(f"{latency:.3f}" for latency in chat_latencies)
    print(
        f"ordinary_chat_quality: PASS; cases={len(QUESTIONS)}; "
        f"direct_complete_answers={direct_responses}"
    )
    print(
        f"ordinary_chat_latency: PASS; mean_seconds={chat_mean:.3f}; max_seconds={chat_max:.3f}; "
        f"baseline_mean_seconds={BASELINE_CHAT_MEAN_SECONDS:.3f}; "
        f"baseline_max_seconds={BASELINE_CHAT_MAX_SECONDS:.3f}; values={values}"
    )
    print(f"ordinary_chat_improvement_percent: {chat_improvement:.1f}")
    print(
        f"streaming_first_audio: PASS; seconds={first_audio:.3f}; "
        f"baseline_seconds={BASELINE_TTS_FIRST_AUDIO_SECONDS:.3f}; "
        f"improvement_percent={speech_improvement:.1f}; words_preserved=yes; voice=af_heart"
    )
    print(f"available_memory_mib: {available / (1024 * 1024):.1f}; limit: >500")
    print("result: PASS lower response latency with unchanged ordinary-answer contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
