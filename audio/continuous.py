"""Continuous AT-CSP1 capture and physical-mute-aware utterance segmentation."""

from __future__ import annotations

import math
import os
import queue
import subprocess
import tempfile
import threading
import time
import wave
from array import array
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

SAMPLE_RATE = 16_000
CHANNELS = 1
SAMPLE_WIDTH = 2
DEFAULT_CAPTURE_DEVICE = "plughw:CARD=Device,DEV=0"


class ContinuousCaptureError(RuntimeError):
    """Raised when the persistent ALSA stream cannot continue."""


def pcm_rms(chunk: bytes) -> float:
    """Return RMS energy for little-endian signed 16-bit PCM."""

    samples = array("h")
    samples.frombytes(chunk)
    if not samples:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in samples) / len(samples))


@dataclass(frozen=True)
class VoiceSegment:
    """One in-memory utterance; PCM is deleted after its temporary transcription WAV."""

    pcm: bytes
    started_at: float
    ended_at: float
    sample_rate: int
    peak_rms: float

    @property
    def duration_seconds(self) -> float:
        return len(self.pcm) / (self.sample_rate * CHANNELS * SAMPLE_WIDTH)


class VoiceSegmenter:
    """Segment voice using the measured AT-CSP1 physical mute noise floors."""

    def __init__(
        self,
        *,
        sample_rate: int = SAMPLE_RATE,
        chunk_ms: int = 100,
        pre_roll_ms: int = 300,
        start_rms: float = 700.0,
        end_rms: float = 350.0,
        start_windows: int = 2,
        end_silence_ms: int = 400,
        max_utterance_seconds: float = 12.0,
    ) -> None:
        if sample_rate <= 0 or chunk_ms <= 0:
            raise ValueError("sample_rate and chunk_ms must be positive")
        if pre_roll_ms < chunk_ms:
            raise ValueError("pre_roll_ms must be at least one chunk")
        if start_rms <= end_rms:
            raise ValueError("start_rms must be greater than end_rms")
        if start_windows < 1:
            raise ValueError("start_windows must be positive")
        if end_silence_ms < chunk_ms:
            raise ValueError("end_silence_ms must be at least one chunk")
        if max_utterance_seconds <= 0:
            raise ValueError("max_utterance_seconds must be positive")

        self.sample_rate = sample_rate
        self.chunk_ms = chunk_ms
        self.start_rms = start_rms
        self.end_rms = end_rms
        self.start_windows = start_windows
        self.end_windows = max(1, math.ceil(end_silence_ms / chunk_ms))
        self.max_windows = max(1, math.ceil(max_utterance_seconds * 1000 / chunk_ms))
        self.chunk_bytes = sample_rate * CHANNELS * SAMPLE_WIDTH * chunk_ms // 1000
        self._pre_roll: deque[bytes] = deque(maxlen=max(1, math.ceil(pre_roll_ms / chunk_ms)))
        self._active_frames: list[bytes] = []
        self._high_windows = 0
        self._low_windows = 0
        self._started_at = 0.0
        self._peak_rms = 0.0

    @property
    def active(self) -> bool:
        return bool(self._active_frames)

    def process(self, chunk: bytes, *, now: float | None = None) -> tuple[bool, VoiceSegment | None]:
        """Consume one exact PCM window and return `(speech_started, completed_segment)`."""

        if len(chunk) != self.chunk_bytes:
            raise ValueError(f"PCM chunk has {len(chunk)} bytes; expected {self.chunk_bytes}")
        observed_at = time.monotonic() if now is None else now
        energy = pcm_rms(chunk)

        if not self.active:
            self._pre_roll.append(chunk)
            self._high_windows = self._high_windows + 1 if energy >= self.start_rms else 0
            if self._high_windows < self.start_windows:
                return False, None

            self._active_frames = list(self._pre_roll)
            self._started_at = observed_at - (len(self._active_frames) * self.chunk_ms / 1000)
            self._peak_rms = max(pcm_rms(frame) for frame in self._active_frames)
            self._low_windows = 0
            return True, None

        self._active_frames.append(chunk)
        self._peak_rms = max(self._peak_rms, energy)
        self._low_windows = self._low_windows + 1 if energy <= self.end_rms else 0
        reached_silence = self._low_windows >= self.end_windows
        reached_limit = len(self._active_frames) >= self.max_windows
        if not reached_silence and not reached_limit:
            return False, None

        frames = self._active_frames
        segment = VoiceSegment(
            pcm=b"".join(frames),
            started_at=self._started_at,
            ended_at=observed_at,
            sample_rate=self.sample_rate,
            peak_rms=self._peak_rms,
        )
        trailing = frames[-self._pre_roll.maxlen :]
        self._pre_roll.clear()
        self._pre_roll.extend(trailing)
        self._active_frames = []
        self._high_windows = 0
        self._low_windows = 0
        self._started_at = 0.0
        self._peak_rms = 0.0
        return False, segment


class ContinuousMicrophone:
    """Own one long-running `arecord` process and publish in-memory voice segments."""

    def __init__(
        self,
        *,
        device: str | None = None,
        on_speech_start: Callable[[], None] | None = None,
        segmenter: VoiceSegmenter | None = None,
    ) -> None:
        self.device = device or os.environ.get(
            "GEMMA_AUDIO_CAPTURE_DEVICE", DEFAULT_CAPTURE_DEVICE
        )
        self.on_speech_start = on_speech_start
        self.segmenter = segmenter or VoiceSegmenter(
            start_rms=float(os.environ.get("GEMMA_VOICE_START_RMS", "700")),
            end_rms=float(os.environ.get("GEMMA_VOICE_END_RMS", "350")),
            end_silence_ms=int(os.environ.get("GEMMA_VOICE_END_MS", "400")),
        )
        self.segments: queue.Queue[VoiceSegment] = queue.Queue()
        self.ready = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._process_lock = threading.Lock()
        self.last_error: BaseException | None = None
        self.last_rms = 0.0
        self.max_rms = 0.0
        self.windows_read = 0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self.ready.clear()
        self.last_error = None
        self._thread = threading.Thread(target=self._capture_loop, name="gemma-microphone", daemon=True)
        self._thread.start()
        if not self.ready.wait(timeout=3):
            raise ContinuousCaptureError("microphone stream did not become ready within 3 seconds")
        if self.last_error is not None:
            raise ContinuousCaptureError(str(self.last_error)) from self.last_error

    def stop(self) -> None:
        self._stop.set()
        with self._process_lock:
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
        if self._thread is not None:
            self._thread.join(timeout=3)

    def get(self, timeout: float | None = None) -> VoiceSegment:
        if self.last_error is not None and self.segments.empty():
            raise ContinuousCaptureError(str(self.last_error)) from self.last_error
        return self.segments.get(timeout=timeout)

    @staticmethod
    def _read_exact(stream, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            chunk = stream.read(remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _capture_loop(self) -> None:
        command = [
            "arecord",
            "-q",
            "-D",
            self.device,
            "-t",
            "raw",
            "-f",
            "S16_LE",
            "-c",
            str(CHANNELS),
            "-r",
            str(self.segmenter.sample_rate),
        ]
        process: subprocess.Popen[bytes] | None = None
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with self._process_lock:
                self._process = process
            if process.stdout is None:
                raise ContinuousCaptureError("arecord stdout pipe is unavailable")
            self.ready.set()
            while not self._stop.is_set():
                chunk = self._read_exact(process.stdout, self.segmenter.chunk_bytes)
                if len(chunk) != self.segmenter.chunk_bytes:
                    if self._stop.is_set():
                        break
                    detail = ""
                    if process.stderr is not None:
                        detail = process.stderr.read().decode(errors="replace").strip()
                    raise ContinuousCaptureError(detail or "ALSA capture stream ended unexpectedly")
                self.last_rms = pcm_rms(chunk)
                self.max_rms = max(self.max_rms, self.last_rms)
                self.windows_read += 1
                started, segment = self.segmenter.process(chunk)
                if started and self.on_speech_start is not None:
                    self.on_speech_start()
                if segment is not None:
                    self.segments.put(segment)
        except BaseException as exc:
            if not self._stop.is_set():
                self.last_error = exc
            self.ready.set()
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            with self._process_lock:
                self._process = None


@contextmanager
def temporary_segment_wav(segment: VoiceSegment) -> Iterator[str]:
    """Expose an in-memory segment as a temporary Whisper-compatible WAV."""

    with tempfile.TemporaryDirectory(prefix="gemma-utterance-") as temporary_dir:
        path = Path(temporary_dir) / "utterance.wav"
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(CHANNELS)
            wav_file.setsampwidth(SAMPLE_WIDTH)
            wav_file.setframerate(segment.sample_rate)
            wav_file.writeframes(segment.pcm)
        yield str(path)
