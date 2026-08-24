"""Cancellable speech playback for physical voice barge-in."""

from __future__ import annotations

import os
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

from .tts import streaming_chunks, synthesize

DEFAULT_PLAYBACK_DEVICE = "plughw:CARD=Device,DEV=0"


class InterruptibleSpeechError(RuntimeError):
    """Raised when synthesis or uncancelled playback fails."""


class InterruptibleSpeech:
    """Synthesize in the background and let the latest human turn cancel playback."""

    def __init__(
        self,
        *,
        device: str | None = None,
        on_playback_start: Callable[[], None] | None = None,
    ) -> None:
        self.device = device or os.environ.get(
            "GEMMA_AUDIO_PLAYBACK_DEVICE", DEFAULT_PLAYBACK_DEVICE
        )
        self.on_playback_start = on_playback_start
        self.speaking = threading.Event()
        self._lock = threading.Lock()
        self._generation = 0
        self._process: subprocess.Popen[str] | None = None
        self._latest_thread: threading.Thread | None = None
        self._threads: set[threading.Thread] = set()
        self._threads_lock = threading.Lock()
        self._synthesis_lock = threading.Lock()
        self.last_error: BaseException | None = None
        self.last_started_at: float | None = None
        self.last_cancel_seconds: float | None = None

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def say(self, text: str, *, words_per_minute: int = 135, replace: bool = True) -> int:
        """Begin speaking asynchronously and return the response generation."""

        clean = " ".join(text.split())
        if not clean:
            raise ValueError("text must not be empty")
        if replace:
            self.interrupt()
        with self._lock:
            token = self._generation
        thread = self._launch(
            self._synthesize_and_play,
            (token, clean, words_per_minute),
            f"gemma-speech-{token}",
        )
        self._latest_thread = thread
        return token

    def play_file(self, wav_path: str | os.PathLike[str], *, replace: bool = True) -> int:
        """Play an existing WAV asynchronously; used by the cancellation verifier."""

        path = Path(wav_path).expanduser().resolve()
        if not path.is_file():
            raise InterruptibleSpeechError(f"audio file does not exist: {path}")
        if replace:
            self.interrupt()
        with self._lock:
            token = self._generation
        thread = self._launch(
            self._play,
            (token, str(path)),
            f"gemma-playback-{token}",
        )
        self._latest_thread = thread
        return token

    def interrupt(self) -> float:
        """Invalidate pending speech and stop active `aplay`; return cancellation latency."""

        started = time.monotonic()
        with self._lock:
            self._generation += 1
            process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=0.25)
        self.speaking.clear()
        elapsed = time.monotonic() - started
        self.last_cancel_seconds = elapsed
        return elapsed

    def wait(self, timeout: float | None = None) -> None:
        thread = self._latest_thread
        if thread is not None:
            thread.join(timeout=timeout)
            if thread.is_alive():
                raise TimeoutError("speech did not finish before the timeout")
        if self.last_error is not None:
            error = self.last_error
            self.last_error = None
            raise InterruptibleSpeechError(str(error)) from error

    def close(self, timeout: float = 30.0) -> None:
        """Cancel playback and wait for any native synthesis calls before interpreter exit."""

        self.interrupt()
        deadline = time.monotonic() + timeout
        while True:
            with self._threads_lock:
                threads = list(self._threads)
            if not threads:
                return
            for thread in threads:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("speech workers did not stop before shutdown timeout")
                thread.join(timeout=remaining)

    def _launch(self, target, args: tuple, name: str) -> threading.Thread:
        def run() -> None:
            try:
                target(*args)
            finally:
                with self._threads_lock:
                    self._threads.discard(threading.current_thread())

        thread = threading.Thread(target=run, name=name, daemon=True)
        with self._threads_lock:
            self._threads.add(thread)
        thread.start()
        return thread

    def _is_current(self, token: int) -> bool:
        with self._lock:
            return token == self._generation

    def _synthesize_and_play(self, token: int, text: str, words_per_minute: int) -> None:
        completed = object()
        pending: queue.Queue[str | BaseException | object] = queue.Queue()

        try:
            with tempfile.TemporaryDirectory(prefix="gemma-interruptible-speech-") as directory:
                chunks = streaming_chunks(text)

                def produce() -> None:
                    try:
                        for chunk in chunks:
                            if not self._is_current(token):
                                break
                            with self._synthesis_lock:
                                path = synthesize(
                                    chunk,
                                    directory,
                                    words_per_minute=words_per_minute,
                                )
                            if not self._is_current(token):
                                break
                            pending.put(path)
                    except BaseException as exc:
                        pending.put(exc)
                    finally:
                        pending.put(completed)

                producer = threading.Thread(
                    target=produce,
                    name=f"gemma-synthesis-{token}",
                    daemon=True,
                )
                producer.start()
                try:
                    while self._is_current(token):
                        item = pending.get()
                        if item is completed:
                            break
                        if isinstance(item, BaseException):
                            raise item
                        self._play(token, item)
                finally:
                    producer.join(timeout=30)
                    if producer.is_alive():
                        raise TimeoutError("speech synthesis did not stop within 30 seconds")
        except BaseException as exc:
            if self._is_current(token):
                self.last_error = exc

    def _play(self, token: int, path: str) -> None:
        process: subprocess.Popen[str] | None = None
        try:
            with self._lock:
                if token != self._generation:
                    return
                process = subprocess.Popen(
                    ["aplay", "-q", "-D", self.device, path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                self._process = process
                self.last_started_at = time.monotonic()
                self.speaking.set()
            if self.on_playback_start is not None:
                self.on_playback_start()
            stdout, stderr = process.communicate(timeout=60)
            if process.returncode != 0 and self._is_current(token):
                detail = stderr.strip() or stdout.strip() or "unknown aplay error"
                raise InterruptibleSpeechError(f"ALSA playback failed: {detail}")
        except subprocess.TimeoutExpired as exc:
            if process is not None:
                process.kill()
                process.communicate()
            if self._is_current(token):
                self.last_error = InterruptibleSpeechError("ALSA playback exceeded 60 seconds")
        except BaseException as exc:
            if self._is_current(token):
                self.last_error = exc
        finally:
            with self._lock:
                if self._process is process:
                    self._process = None
                if token == self._generation:
                    self.speaking.clear()
