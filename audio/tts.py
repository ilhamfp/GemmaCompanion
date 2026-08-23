"""Resident Kokoro text-to-speech with queued ALSA playback."""

from __future__ import annotations

import ctypes.util
import hashlib
import importlib.metadata
import logging
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import types
import unicodedata
import uuid
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .speaker import play_audio

if TYPE_CHECKING:
    import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ESPEAK = REPO_ROOT / ".runtime" / "espeak" / "usr" / "bin" / "espeak-ng"
MODEL_PATH = REPO_ROOT / "models" / "kokoro-v1.0.onnx"
VOICES_PATH = REPO_ROOT / "models" / "voices-v1.0.bin"
CACHE_DIR = REPO_ROOT / "artifacts" / "tts-cache"

DEFAULT_VOICE = "af_heart"
DEFAULT_BASE_SPEED = 1.08
DEFAULT_SAMPLE_RATE = 24_000

LOOK_ANNOUNCEMENT = "Let me look over there."
GLASSES_CONFIRMATION = "You want me to find your glasses, is that right?"
ONE_MOMENT = "One moment."
ELDERLY_NOT_FOUND = (
    "I couldn't find the red umbrella from here. Please check its usual place."
)
AKINATOR_FIXED_PHRASES = [LOOK_ANNOUNCEMENT]
ELDERLY_FIXED_PHRASES = [GLASSES_CONFIRMATION, ONE_MOMENT, ELDERLY_NOT_FOUND]
FIXED_PHRASES = [*AKINATOR_FIXED_PHRASES, *ELDERLY_FIXED_PHRASES]

_LOGGER = logging.getLogger(__name__)
_ENGINE: TTSEngine | None = None
_ENGINE_FAILURE: Exception | None = None
_ENGINE_LOCK = threading.Lock()
_FALLBACK_WARNED = False
_PRE_RENDERED: dict[str, str] = {}


class TTSError(RuntimeError):
    """Raised when speech synthesis or queued playback fails."""


def _first_existing(candidates: list[Path]) -> Path | None:
    return next((path for path in candidates if path.exists()), None)


def _install_espeak_loader_shim() -> None:
    """Use the existing user/system eSpeak library on unsupported wheel platforms."""

    try:
        import espeakng_loader  # noqa: F401

        return
    except ImportError:
        pass

    data_path = _first_existing(
        [
            REPO_ROOT / ".runtime" / "espeak" / "usr" / "lib" / "aarch64-linux-gnu" / "espeak-ng-data",
            Path("/usr/lib/aarch64-linux-gnu/espeak-ng-data"),
            Path("/usr/share/espeak-ng-data"),
        ]
    )
    configured_library = os.environ.get("PHONEMIZER_ESPEAK_LIBRARY")
    library_path = configured_library or ctypes.util.find_library("espeak-ng")
    if not library_path:
        library = _first_existing(
            [
                REPO_ROOT
                / ".runtime"
                / "espeak"
                / "usr"
                / "lib"
                / "aarch64-linux-gnu"
                / "libespeak-ng.so.1",
                Path("/lib/aarch64-linux-gnu/libespeak-ng.so.1"),
            ]
        )
        library_path = str(library) if library else None
    if not data_path or not library_path:
        raise TTSError("eSpeak NG shared library/data not found for Kokoro phonemization")

    os.environ["PHONEMIZER_ESPEAK_LIBRARY"] = str(library_path)
    shim = types.ModuleType("espeakng_loader")
    shim.get_data_path = lambda: str(data_path)  # type: ignore[attr-defined]
    shim.get_library_path = lambda: str(library_path)  # type: ignore[attr-defined]
    sys.modules["espeakng_loader"] = shim


class TTSEngine:
    """CPU-only Kokoro model loaded once and reused for every utterance."""

    name = "kokoro-onnx"

    def __init__(self, *, voice: str | None = None, base_speed: float | None = None) -> None:
        started = time.monotonic()
        _install_espeak_loader_shim()
        if not MODEL_PATH.is_file() or not VOICES_PATH.is_file():
            raise TTSError("Kokoro model files are missing; run scripts/bootstrap_tts.sh")

        import onnxruntime as ort
        from kokoro_onnx import Kokoro

        self.voice = voice or os.environ.get("GEMMA_TTS_VOICE", DEFAULT_VOICE)
        self.base_speed = float(
            base_speed
            if base_speed is not None
            else os.environ.get("GEMMA_TTS_SPEED", str(DEFAULT_BASE_SPEED))
        )
        if not 0.5 <= self.base_speed <= 2.0:
            raise TTSError("GEMMA_TTS_SPEED must be between 0.5 and 2.0")
        thread_count = int(os.environ.get("GEMMA_TTS_THREADS", "6"))
        if thread_count < 1:
            raise TTSError("GEMMA_TTS_THREADS must be positive")
        options = ort.SessionOptions()
        options.intra_op_num_threads = thread_count
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(
            str(MODEL_PATH),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self._model = Kokoro.from_session(session, str(VOICES_PATH))
        if self.voice not in self._model.get_voices():
            raise TTSError(f"Kokoro voice is unavailable: {self.voice}")
        self.version = importlib.metadata.version("kokoro-onnx")
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self.load_seconds = time.monotonic() - started

    def synth(self, text: str, speed: float = 1.0) -> tuple["np.ndarray", int]:
        """Return mono floating-point PCM and its sample rate."""

        clean = speech_friendly_text(text)
        if not clean:
            raise ValueError("text must not be empty")
        # Kokoro spends a measurable extra graph step on comma prosody on this
        # six-core Jetson. Short spoken replies remain natural without it, and
        # every word and sentence boundary is preserved.
        model_text = clean.replace(",", "")
        effective_speed = self.base_speed * speed
        if not 0.5 <= effective_speed <= 2.0:
            raise ValueError("effective Kokoro speed must be between 0.5 and 2.0")
        audio, sample_rate = self._model.create(
            model_text,
            voice=self.voice,
            speed=effective_speed,
            lang="en-us",
            # Preserve the model's own punctuation prosody without a second
            # full-array pause-analysis pass on this latency-bound CPU.
            sentence_pause=0.0,
            clause_pause=0.0,
        )
        return audio, sample_rate


def _engine() -> TTSEngine:
    global _ENGINE, _ENGINE_FAILURE
    if _ENGINE is not None:
        return _ENGINE
    if _ENGINE_FAILURE is not None:
        raise TTSError(str(_ENGINE_FAILURE)) from _ENGINE_FAILURE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            try:
                _ENGINE = TTSEngine()
            except Exception as exc:
                _ENGINE_FAILURE = exc
                raise TTSError(str(exc)) from exc
    return _ENGINE


def get_engine() -> TTSEngine:
    """Return the process-wide resident engine (primarily for verification)."""

    return _engine()


def _warn_fallback(exc: Exception) -> None:
    global _FALLBACK_WARNED
    if not _FALLBACK_WARNED:
        _LOGGER.warning("Kokoro TTS unavailable; falling back to eSpeak NG: %s", exc)
        _FALLBACK_WARNED = True


def _espeak_binary() -> str:
    configured = os.environ.get("GEMMA_ESPEAK_PATH")
    if configured:
        return configured
    system = shutil.which("espeak-ng")
    if system:
        return system
    if RUNTIME_ESPEAK.is_file():
        return str(RUNTIME_ESPEAK)
    raise TTSError("eSpeak NG not found; run the documented runtime bootstrap")


_SMALL_NUMBERS = {
    0: "zero",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
}
_TENS = {
    20: "twenty",
    30: "thirty",
    40: "forty",
    50: "fifty",
    60: "sixty",
    70: "seventy",
    80: "eighty",
    90: "ninety",
}


def _number_words(value: int) -> str:
    if value < 20:
        return _SMALL_NUMBERS[value]
    if value < 100:
        tens, remainder = divmod(value, 10)
        return _TENS[tens * 10] + (f"-{_SMALL_NUMBERS[remainder]}" if remainder else "")
    hundreds, remainder = divmod(value, 100)
    suffix = f" {_number_words(remainder)}" if remainder else ""
    return f"{_SMALL_NUMBERS[hundreds]} hundred{suffix}"


def speech_friendly_text(text: str) -> str:
    """Remove visual-only formatting and expand short digit sequences."""

    clean = re.sub(r"```.*?```", " ", str(text), flags=re.DOTALL)
    clean = re.sub(r"`([^`]*)`", r"\1", clean)
    clean = re.sub(r"!\[([^]]*)\]\([^)]*\)", r"\1", clean)
    clean = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", clean)
    clean = re.sub(r"(?m)^\s*(?:[-*+] |\d+[.)]\s+|#{1,6}\s*)", "", clean)
    clean = re.sub(r"[*_~>|]", "", clean)
    clean = "".join(
        character
        for character in clean
        if not unicodedata.category(character).startswith(("So", "Sk"))
    )
    clean = re.sub(
        r"\b\d{1,3}\b",
        lambda match: _number_words(int(match.group(0))),
        clean,
    )
    return " ".join(clean.split()).strip()


def _validate_wpm(words_per_minute: int) -> None:
    if not 80 <= words_per_minute <= 220:
        raise ValueError("words_per_minute must be between 80 and 220")


def _model_speed(words_per_minute: int) -> float:
    _validate_wpm(words_per_minute)
    return words_per_minute / 135.0


def _write_wav(path: Path, audio: "np.ndarray", sample_rate: int) -> None:
    import numpy as np

    pcm = (np.clip(np.asarray(audio), -1.0, 1.0) * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())


def _synthesize_espeak(text: str, path: Path, words_per_minute: int) -> None:
    result = subprocess.run(
        [_espeak_binary(), "-s", str(words_per_minute), "-w", str(path), text],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown eSpeak NG error"
        raise TTSError(f"speech synthesis failed: {detail}")


def _render(text: str, path: Path, words_per_minute: int) -> None:
    try:
        engine = _engine()
        audio, sample_rate = engine.synth(text, speed=_model_speed(words_per_minute))
        _write_wav(path, audio, sample_rate)
    except Exception as exc:
        _warn_fallback(exc)
        _synthesize_espeak(text, path, words_per_minute)
    if not path.is_file() or path.stat().st_size <= 44:
        raise TTSError("speech synthesis produced no PCM samples")


def synthesize(
    text: str,
    output_dir: str | os.PathLike[str] | None = None,
    *,
    words_per_minute: int = 135,
) -> str:
    """Synthesize speech to a unique WAV and return its absolute path."""

    clean = speech_friendly_text(text)
    if not clean:
        raise ValueError("text must not be empty")
    _validate_wpm(words_per_minute)
    destination = Path(output_dir or Path.cwd() / "captures" / "audio").expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / f"speech-{uuid.uuid4().hex}.wav"
    _render(clean, path, words_per_minute)
    return str(path)


@dataclass
class _PlaybackTicket:
    path: str
    started: threading.Event = field(default_factory=threading.Event)
    started_at: float | None = None


_PLAYBACK_QUEUE: queue.Queue[_PlaybackTicket] = queue.Queue()
_PLAYBACK_THREAD: threading.Thread | None = None
_PLAYBACK_LOCK = threading.Lock()
_PLAYBACK_ERROR: Exception | None = None
_LAST_PLAYBACK_STARTED_AT: float | None = None
_PLAYBACK_ACTIVE = threading.Event()


def _playback_worker() -> None:
    global _PLAYBACK_ERROR, _LAST_PLAYBACK_STARTED_AT
    while True:
        ticket = _PLAYBACK_QUEUE.get()

        def mark_started() -> None:
            global _LAST_PLAYBACK_STARTED_AT
            ticket.started_at = time.monotonic()
            _LAST_PLAYBACK_STARTED_AT = ticket.started_at
            _PLAYBACK_ACTIVE.set()
            ticket.started.set()

        try:
            play_audio(ticket.path, on_start=mark_started)
        except Exception as exc:
            _PLAYBACK_ERROR = exc
            ticket.started.set()
        finally:
            _PLAYBACK_ACTIVE.clear()
            _PLAYBACK_QUEUE.task_done()


def _ensure_playback_worker() -> None:
    global _PLAYBACK_THREAD
    with _PLAYBACK_LOCK:
        if _PLAYBACK_THREAD is None or not _PLAYBACK_THREAD.is_alive():
            _PLAYBACK_THREAD = threading.Thread(
                target=_playback_worker,
                name="gemma-audio-playback",
                daemon=True,
            )
            _PLAYBACK_THREAD.start()


def _enqueue(path: str) -> _PlaybackTicket:
    _ensure_playback_worker()
    ticket = _PlaybackTicket(path)
    _PLAYBACK_QUEUE.put(ticket)
    return ticket


def wait_until_silent() -> None:
    """Block until queued/current playback completes, then surface playback errors."""

    global _PLAYBACK_ERROR
    _PLAYBACK_QUEUE.join()
    if _PLAYBACK_ERROR is not None:
        error = _PLAYBACK_ERROR
        _PLAYBACK_ERROR = None
        raise TTSError(f"queued playback failed: {error}") from error


def last_playback_started_at() -> float | None:
    """Return the latest aplay-start timestamp for the latency verifier."""

    return _LAST_PLAYBACK_STARTED_AT


def playback_active() -> bool:
    """Return whether the single worker is currently playing a clip."""

    return _PLAYBACK_ACTIVE.is_set()


def _fixed_wpm(phrase: str) -> int:
    return 120 if phrase in ELDERLY_FIXED_PHRASES else 135


def prerender(phrases: list[str]) -> dict[str, str]:
    """Render fixed phrases once and return their text-to-WAV mapping."""

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    rendered: dict[str, str] = {}
    for phrase in phrases:
        clean = speech_friendly_text(phrase)
        if not clean:
            raise ValueError("pre-render phrases must not be empty")
        words_per_minute = _fixed_wpm(clean)
        cache_key = f"{DEFAULT_VOICE}|{DEFAULT_BASE_SPEED}|{words_per_minute}|{clean}"
        digest = hashlib.sha256(cache_key.encode("utf-8")).hexdigest()[:16]
        path = CACHE_DIR / f"{digest}.wav"
        if not path.is_file() or path.stat().st_size <= 44:
            _render(clean, path, words_per_minute)
        _PRE_RENDERED[clean] = str(path)
        rendered[phrase] = str(path)
    return rendered


def speak_cached(key: str) -> None:
    """Start a pre-rendered clip and return without waiting for it to finish."""

    clean = speech_friendly_text(key)
    path = _PRE_RENDERED.get(clean)
    if path is None:
        path = prerender([clean])[clean]
    ticket = _enqueue(path)
    if not ticket.started.wait(timeout=0.2):
        raise TTSError("cached playback did not start within 0.2 seconds")
    if ticket.started_at is None:
        wait_until_silent()


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]


def _streaming_chunks(text: str, *, max_words: int = 4) -> list[str]:
    """Keep first-audio latency bounded while preserving sentence order."""

    chunks: list[str] = []
    for sentence in _sentences(text):
        words = sentence.split()
        chunks.extend(
            " ".join(words[index : index + max_words])
            for index in range(0, len(words), max_words)
        )
    return chunks


def speak(text: str, *, words_per_minute: int = 135) -> None:
    """Synthesize, enqueue, and finish speaking text through one playback worker."""

    clean = speech_friendly_text(text)
    if not clean:
        raise ValueError("text must not be empty")
    _validate_wpm(words_per_minute)
    cached = _PRE_RENDERED.get(clean)
    if cached and words_per_minute == _fixed_wpm(clean):
        _enqueue(cached)
        wait_until_silent()
        return

    # Sentences retain their order and are further divided into short PCM
    # windows because the CPU ONNX graph emits only complete tensors. Each
    # window is queued as soon as it is ready, so playback overlaps rendering.
    for chunk in _streaming_chunks(clean):
        _enqueue(synthesize(chunk, words_per_minute=words_per_minute))
    wait_until_silent()
