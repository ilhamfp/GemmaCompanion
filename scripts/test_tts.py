#!/usr/bin/env python3
"""M9 acceptance test for resident natural TTS and queued playback."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from audio.tts import (  # noqa: E402
    LOOK_ANNOUNCEMENT,
    _write_wav,
    get_engine,
    last_playback_started_at,
    prerender,
    speak,
    speak_cached,
    wait_until_silent,
)

TEST_SENTENCE = "Your glasses are on the table beside the sofa, next to the cup."
FIRST_AUDIO_LIMIT = 1.5
TOTAL_LIMIT = 3.0
CACHED_LIMIT = 0.2
FREE_LIMIT_GIB = 2.0
TTS_RSS_LIMIT_MIB = 800.0


def _available_gib() -> float:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / (1024 * 1024)
    raise RuntimeError("MemAvailable missing from /proc/meminfo")


def _rss_mib() -> float:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    raise RuntimeError("VmRSS missing from /proc/self/status")


def _assert_gemma_running() -> None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/props", timeout=2) as response:
            if response.status != 200:
                raise RuntimeError(f"Gemma server returned HTTP {response.status}")
    except Exception as exc:
        raise RuntimeError("Gemma server must be running before scripts/test_tts.py") from exc


def _companion_service_running() -> bool:
    return subprocess.run(
        ["systemctl", "is-active", "--quiet", "gemma-companion.service"],
        check=False,
    ).returncode == 0


def _wait_for_playback_start(after: float, timeout: float = 10.0) -> float:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        started = last_playback_started_at()
        if started is not None and started >= after:
            return started
        time.sleep(0.002)
    raise TimeoutError("playback worker did not start")


def main() -> int:
    _assert_gemma_running()
    artifacts = REPO_ROOT / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    free_before_gib = _available_gib()
    companion_running = _companion_service_running()
    rss_before = _rss_mib()
    engine = get_engine()
    rss_after = _rss_mib()
    tts_resident_mib = max(0.0, rss_after - rss_before)

    # Warm the already-resident graph and the acceptance sentence's tensor
    # shapes before enforcing the explicitly warm latency limits.
    engine.synth(TEST_SENTENCE, speed=1.0)
    total_started = time.monotonic()
    audio, sample_rate = engine.synth(TEST_SENTENCE, speed=1.0)
    total_seconds = time.monotonic() - total_started
    sample_path = artifacts / "tts-sample.wav"
    _write_wav(sample_path, audio, sample_rate)

    wait_until_silent()
    first_call_at = time.monotonic()
    speech_error: list[BaseException] = []

    def run_speech() -> None:
        try:
            speak(TEST_SENTENCE)
        except BaseException as exc:  # hand worker errors back to the main test thread
            speech_error.append(exc)

    speech_thread = threading.Thread(target=run_speech, name="tts-first-audio-test")
    speech_thread.start()
    first_audio_at = _wait_for_playback_start(first_call_at)
    first_audio_seconds = first_audio_at - first_call_at
    speech_thread.join(timeout=30)
    if speech_thread.is_alive():
        raise TimeoutError("speak() did not finish within 30 seconds")
    if speech_error:
        raise speech_error[0]

    prerender([LOOK_ANNOUNCEMENT])
    wait_until_silent()
    cached_call_at = time.monotonic()
    speak_cached(LOOK_ANNOUNCEMENT)
    cached_play_at = _wait_for_playback_start(cached_call_at)
    cached_play_seconds = cached_play_at - cached_call_at
    wait_until_silent()

    free_available_gib = _available_gib()
    production_available_gib = (
        free_before_gib if companion_running else free_available_gib
    )
    print(
        f"engine: {engine.name} {engine.version}; voice: {engine.voice}; "
        f"sample_rate: {sample_rate}; provider: CPUExecutionProvider"
    )
    print(f"load_seconds: {engine.load_seconds:.3f}")
    print(f"first_audio_seconds: {first_audio_seconds:.3f}; limit: <{FIRST_AUDIO_LIMIT:.1f}")
    print(f"total_seconds: {total_seconds:.3f}; limit: <{TOTAL_LIMIT:.1f}")
    print(f"cached_play_seconds: {cached_play_seconds:.3f}; limit: <{CACHED_LIMIT:.1f}")
    print(
        f"production_available_gib: {production_available_gib:.3f}; "
        f"limit: >{FREE_LIMIT_GIB:.1f}; duplicate_test_available_gib: {free_available_gib:.3f}; "
        f"tts_resident_mib: {tts_resident_mib:.1f}; limit: <={TTS_RSS_LIMIT_MIB:.0f}"
    )
    print(f"test_wav: {sample_path}")

    failures = []
    if first_audio_seconds >= FIRST_AUDIO_LIMIT:
        failures.append(f"first audio {first_audio_seconds:.3f}s is not under {FIRST_AUDIO_LIMIT}s")
    if total_seconds >= TOTAL_LIMIT:
        failures.append(f"total synthesis {total_seconds:.3f}s is not under {TOTAL_LIMIT}s")
    if cached_play_seconds >= CACHED_LIMIT:
        failures.append(f"cached playback {cached_play_seconds:.3f}s is not under {CACHED_LIMIT}s")
    if production_available_gib <= FREE_LIMIT_GIB:
        failures.append(
            f"production RAM {production_available_gib:.3f} GiB is not above {FREE_LIMIT_GIB}"
        )
    if free_available_gib <= 0.5:
        failures.append(
            f"duplicate verifier left only {free_available_gib:.3f} GiB available"
        )
    if tts_resident_mib > TTS_RSS_LIMIT_MIB:
        failures.append(f"TTS RSS {tts_resident_mib:.1f} MiB exceeds {TTS_RSS_LIMIT_MIB:.0f} MiB")
    if failures:
        print("result: FAIL " + "; ".join(failures))
        return 1

    print("result: PASS natural resident CPU TTS meets warm, cached, and memory limits")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
