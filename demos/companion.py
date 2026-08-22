"""Persistent, physically interruptible voice-and-vision companion session."""

from __future__ import annotations

import json
import queue
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent.gemma import GemmaClient
from audio.continuous import ContinuousMicrophone, VoiceSegment, temporary_segment_wav
from audio.interruptible import InterruptibleSpeech
from audio.fast_stt import transcribe_fast
from camera.capture import capture_image
from camera.obsbot import look_center, look_down, look_left, look_right, look_up
from audio.volume import VOLUME_STEP, adjust_volume, set_volume

MIN_AVAILABLE_BYTES = 500 * 1024 * 1024
READY_CUE = "Hey, Gemma here!"
VISION_PROMPT = """Describe only what is clearly visible in this fresh camera image.
Use one or two short spoken sentences. Name the main concrete objects and their useful physical locations.
Do not mention pixels, the image, or anything outside the view. Do not invent uncertain details."""
CONVERSATION_PROMPT = """You are Gemma Companion, an offline embodied assistant on a Jetson.
Reply in one or two short spoken sentences with normal punctuation and no markdown.
Never claim to see something unless it came from a fresh camera observation in this conversation."""


def available_memory_bytes() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable is unavailable")


@dataclass(frozen=True)
class Intent:
    kind: str
    direction: str | None = None
    value: int | None = None


@dataclass(frozen=True)
class CompanionResult:
    action: str
    response: str
    direction: str
    image_path: str | None
    latency_seconds: float


def parse_intent(text: str) -> Intent:
    """Route safety- and latency-critical commands without a model round trip."""

    normalized = " ".join(re.findall(r"[a-z']+", text.casefold()))
    words = set(normalized.split())
    if words & {"stop", "cancel"} or "be quiet" in normalized or "shut up" in normalized:
        return Intent("stop")
    if "go to sleep" in normalized or "stop listening" in normalized:
        return Intent("sleep")
    if "wake up" in normalized or "start listening" in normalized:
        return Intent("wake")

    volume_match = re.search(r"\bvolume(?:\s+(?:to|at))?\s+(\d{1,3})\b", text.casefold())
    if volume_match:
        return Intent("volume_set", value=int(volume_match.group(1)))
    if (
        "volume up" in normalized
        or "speak louder" in normalized
        or "make it louder" in normalized
        or "turn it up" in normalized
    ):
        return Intent("volume_up")
    if (
        "volume down" in normalized
        or "speak quieter" in normalized
        or "make it quieter" in normalized
        or "turn it down" in normalized
    ):
        return Intent("volume_down")

    direction_aliases = {
        "left": {"left", "laugh", "loft"},
        "right": {"right", "write"},
        "up": {"up"},
        "down": {"down"},
        "center": {"center", "centre"},
    }
    direction = next(
        (
            candidate
            for candidate, aliases in direction_aliases.items()
            if words & aliases
        ),
        None,
    )
    movement_words = {"look", "turn", "face", "move", "point"}
    asks_to_see = any(
        phrase in normalized
        for phrase in (
            "what do you see",
            "what can you see",
            "describe what you see",
            "describe the room",
            "what is in front of you",
            "what's in front of you",
            "tell me what you see",
        )
    )
    if direction and (words & movement_words or len(words) == 1):
        return Intent("look_and_describe" if asks_to_see else "look", direction)
    if asks_to_see:
        return Intent("describe")
    return Intent("chat")


class CompanionSession:
    """Latest-turn-wins session coordinating mic, speech, camera, and Gemma."""

    def __init__(
        self,
        *,
        speech: bool = True,
        microphone: bool = True,
        log_dir: str | Path | None = None,
        gemma: GemmaClient | None = None,
        speaker: InterruptibleSpeech | None = None,
        mic: ContinuousMicrophone | None = None,
    ) -> None:
        self.speech_enabled = speech
        self.microphone_enabled = microphone
        self.gemma = gemma or GemmaClient()
        self.speaker = speaker or InterruptibleSpeech()
        self.mic = mic or ContinuousMicrophone(on_speech_start=self._on_speech_start)
        self._stop = threading.Event()
        self._turn_lock = threading.Lock()
        self._camera_lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._turn = 0
        self._capture_turn = 0
        self._direction = "center"
        self._asleep = False
        self._transcription_thread: threading.Thread | None = None
        self._workers: set[threading.Thread] = set()
        self._workers_lock = threading.Lock()
        self._conversation: list[dict[str, str]] = []
        destination = Path(log_dir or Path.cwd() / "logs").expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        self.log_path = destination / f"companion-{stamp}.jsonl"
        self.last_result: CompanionResult | None = None
        self.last_barge_in_at: float | None = None
        self.last_barge_cancel_seconds: float | None = None
        self.last_barge_was_speaking = False
        self.barge_in_count = 0
        self.barge_while_speaking_count = 0
        self.max_active_playback_cancel_seconds = 0.0
        self.last_segment_ended_at: float | None = None
        self.last_transcript_at: float | None = None
        self.last_result_at: float | None = None

    @property
    def direction(self) -> str:
        with self._camera_lock:
            return self._direction

    @property
    def turn(self) -> int:
        with self._turn_lock:
            return self._turn

    def _log(self, action: str, **fields) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            **fields,
        }
        with self._log_lock, self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _new_turn(self) -> int:
        with self._turn_lock:
            self._turn += 1
            return self._turn

    def _is_current(self, token: int) -> bool:
        with self._turn_lock:
            return token == self._turn

    def _on_speech_start(self) -> None:
        self.last_barge_in_at = time.monotonic()
        self.last_barge_was_speaking = self.speaker.speaking.is_set()
        self.barge_in_count += 1
        if self.last_barge_was_speaking:
            self.barge_while_speaking_count += 1
        token = self._new_turn()
        with self._turn_lock:
            self._capture_turn = token
        cancel_seconds = self.speaker.interrupt()
        self.last_barge_cancel_seconds = cancel_seconds
        if self.last_barge_was_speaking:
            self.max_active_playback_cancel_seconds = max(
                self.max_active_playback_cancel_seconds, cancel_seconds
            )
        self._log(
            "BARGE_IN",
            turn=token,
            playback_was_active=self.last_barge_was_speaking,
            playback_cancel_seconds=round(cancel_seconds, 4),
        )
        print("Listening...", flush=True)

    def start(self, *, announce_scene: bool = True) -> None:
        """Start listening, then perform a grounded boot observation and readiness announcement."""

        self.gemma.show()
        if self.microphone_enabled:
            self.mic.start()
            self._transcription_thread = threading.Thread(
                target=self._transcription_loop,
                name="gemma-transcription",
                daemon=True,
            )
            self._transcription_thread.start()
        token = self._new_turn()
        with self._turn_lock:
            self._capture_turn = token
        if announce_scene:
            self._spawn(self._announce_ready, token)
        else:
            self._respond(READY_CUE, token)
        self._log("COMPANION_START", turn=token, microphone=self.microphone_enabled)

    def stop(self) -> None:
        self._stop.set()
        self._new_turn()
        self.speaker.interrupt()
        if self.microphone_enabled:
            self.mic.stop()
        if self._transcription_thread is not None:
            self._transcription_thread.join(timeout=3)
        with self._workers_lock:
            workers = list(self._workers)
        for worker in workers:
            worker.join(timeout=3)
        try:
            self.speaker.close(timeout=30)
        except Exception as exc:
            self._log("SPEECH_SHUTDOWN_ERROR", error=str(exc))
        try:
            look_center()
        except Exception as exc:
            self._log("RECENTER_ERROR", error=str(exc))
        self._log("COMPANION_STOP")

    def request_stop(self) -> None:
        """Ask the foreground loop to stop cleanly from a signal handler."""

        self._stop.set()

    def run_forever(self, *, announce_scene: bool = True) -> None:
        self.start(announce_scene=announce_scene)
        try:
            while not self._stop.wait(0.5):
                if self.microphone_enabled and self.mic.last_error is not None:
                    raise RuntimeError(f"continuous microphone failed: {self.mic.last_error}")
        finally:
            self.stop()

    def submit_text(self, text: str) -> int:
        """Inject a turn for deterministic verification while preserving latest-turn semantics."""

        token = self._new_turn()
        self.speaker.interrupt()
        self._spawn(self.handle_text, text, token)
        return token

    def handle_text(self, text: str, token: int | None = None) -> CompanionResult:
        """Synchronously execute one transcript; direct commands bypass Gemma."""

        started = time.monotonic()
        active_token = self._new_turn() if token is None else token
        clean = " ".join(text.split())
        if not clean:
            raise ValueError("transcript must not be empty")
        print(f"You: {clean}", flush=True)
        intent = parse_intent(clean)
        self._log("TRANSCRIPT", turn=active_token, text=clean, intent=intent.kind)

        if intent.kind == "stop":
            self.speaker.interrupt()
            result = self._result("stop", "Stopped.", None, started)
            self._publish_result(result, active_token, speak=False)
            return result
        if intent.kind == "sleep":
            self._asleep = True
            result = self._result("sleep", "Going idle. Say wake up when you need me.", None, started)
            self._publish_result(result, active_token)
            return result
        if intent.kind == "wake":
            self._asleep = False
            result = self._result("wake", "I'm awake.", None, started)
            self._publish_result(result, active_token)
            return result
        if intent.kind in {"volume_set", "volume_up", "volume_down"}:
            if intent.kind == "volume_set":
                if intent.value is None or not 0 <= intent.value <= 100:
                    result = self._result(
                        "volume_invalid",
                        "Please choose a volume from zero to one hundred percent.",
                        None,
                        started,
                    )
                    self._publish_result(result, active_token)
                    return result
                volume = set_volume(intent.value)
            else:
                delta = VOLUME_STEP if intent.kind == "volume_up" else -VOLUME_STEP
                volume = adjust_volume(delta)
            result = self._result(
                intent.kind,
                f"Volume {volume} percent.",
                None,
                started,
            )
            self._publish_result(result, active_token)
            return result
        if self._asleep:
            result = self._result("ignored_asleep", "", None, started)
            self._publish_result(result, active_token, speak=False)
            return result
        if intent.kind in {"look", "look_and_describe"}:
            assert intent.direction is not None
            self._move(intent.direction, active_token)
            if intent.kind == "look":
                result = self._result(
                    f"look_{intent.direction}", f"Looking {intent.direction}.", None, started
                )
                self._publish_result(result, active_token)
                return result
            return self._describe(active_token, started)
        if intent.kind == "describe":
            return self._describe(active_token, started)
        return self._chat(clean, active_token, started)

    def _spawn(self, target, *args) -> threading.Thread:
        def run() -> None:
            try:
                target(*args)
            except Exception as exc:
                self._log("WORKER_ERROR", worker=getattr(target, "__name__", str(target)), error=str(exc))
                if args and isinstance(args[-1], int) and self._is_current(args[-1]):
                    self._respond("I hit a local error, but I'm still listening.", args[-1])
            finally:
                with self._workers_lock:
                    self._workers.discard(threading.current_thread())

        thread = threading.Thread(target=run, name=f"gemma-{getattr(target, '__name__', 'turn')}", daemon=True)
        with self._workers_lock:
            self._workers.add(thread)
        thread.start()
        return thread

    def _transcription_loop(self) -> None:
        while not self._stop.is_set():
            try:
                segment = self.mic.get(timeout=0.5)
            except queue.Empty:
                continue
            with self._turn_lock:
                token = self._capture_turn
            self._transcribe_segment(segment, token)

    def _transcribe_segment(self, segment: VoiceSegment, token: int) -> None:
        self.last_segment_ended_at = segment.ended_at
        started = time.monotonic()
        try:
            with temporary_segment_wav(segment) as path:
                text = transcribe_fast(path)
        except Exception as exc:
            self._log("TRANSCRIPTION_ERROR", turn=token, error=str(exc))
            return
        latency = time.monotonic() - started
        self.last_transcript_at = time.monotonic()
        self._log(
            "TRANSCRIPTION",
            turn=token,
            text=text,
            latency_seconds=round(latency, 3),
            utterance_seconds=round(segment.duration_seconds, 3),
            peak_rms=round(segment.peak_rms, 1),
        )
        if self._is_current(token):
            self._spawn(self.handle_text, text, token)
        else:
            self._log("STALE_TRANSCRIPT_DISCARDED", turn=token)

    def _announce_ready(self, token: int) -> None:
        try:
            self._move("center", token)
            with self._camera_lock:
                image_path = capture_image(Path.cwd() / "captures" / "companion")
            text, _ = self.gemma.step(
                [
                    {
                        "role": "system",
                        "content": "Reply in one short spoken sentence with no markdown.",
                    },
                    {
                        "role": "user",
                        "content": "Name one or two main objects clearly visible.",
                    },
                ],
                [image_path],
            )
            response = READY_CUE
            self._log(
                "BOOT_OBSERVE",
                turn=token,
                image_path=image_path,
                scene_summary=" ".join(text.split()),
                response=response,
            )
        except Exception as exc:
            response = "Gemma here, but my vision isn't ready yet."
            self._log("BOOT_OBSERVE_FALLBACK", turn=token, error=str(exc))
        self._respond(response, token)

    def _move(self, direction: str, token: int) -> None:
        functions = {
            "left": look_left,
            "right": look_right,
            "up": look_up,
            "down": look_down,
            "center": look_center,
        }
        with self._camera_lock:
            position = functions[direction]()
            self._direction = direction
        self._log(
            "DIRECT_LOOK",
            turn=token,
            direction=direction,
            pan_degrees=position[0],
            tilt_degrees=position[1],
        )

    def _describe(self, token: int, started: float) -> CompanionResult:
        if available_memory_bytes() < MIN_AVAILABLE_BYTES:
            result = self._result(
                "describe_refused_low_memory",
                "I don't have enough free memory to inspect safely.",
                None,
                started,
            )
            self._publish_result(result, token)
            return result
        with self._camera_lock:
            direction = self._direction
            image_path = capture_image(Path.cwd() / "captures" / "companion")
        text, _ = self.gemma.step(
            [
                {"role": "system", "content": CONVERSATION_PROMPT},
                {
                    "role": "user",
                    "content": f"Current physical camera direction: {direction}.\n{VISION_PROMPT}",
                },
            ],
            [image_path],
        )
        result = self._result("describe", text, image_path, started)
        self._publish_result(result, token)
        return result

    def _chat(self, text: str, token: int, started: float) -> CompanionResult:
        if available_memory_bytes() < MIN_AVAILABLE_BYTES:
            result = self._result(
                "chat_refused_low_memory",
                "I don't have enough free memory to answer safely.",
                None,
                started,
            )
            self._publish_result(result, token)
            return result
        messages = [
            {"role": "system", "content": CONVERSATION_PROMPT},
            *self._conversation[-6:],
            {"role": "user", "content": text},
        ]
        response, _ = self.gemma.step(messages)
        if self._is_current(token):
            self._conversation.extend(
                [
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": response},
                ]
            )
        result = self._result("chat", response, None, started)
        self._publish_result(result, token)
        return result

    def _result(
        self,
        action: str,
        response: str,
        image_path: str | None,
        started: float,
    ) -> CompanionResult:
        return CompanionResult(
            action=action,
            response=" ".join(response.split()),
            direction=self.direction,
            image_path=image_path,
            latency_seconds=time.monotonic() - started,
        )

    def _publish_result(self, result: CompanionResult, token: int, *, speak: bool = True) -> None:
        if not self._is_current(token):
            self._log("STALE_RESULT_DISCARDED", turn=token, result_action=result.action)
            return
        self.last_result = result
        self.last_result_at = time.monotonic()
        self._log(
            "COMPANION_RESULT",
            turn=token,
            result_action=result.action,
            direction=result.direction,
            response=result.response,
            image_path=result.image_path,
            latency_seconds=round(result.latency_seconds, 3),
        )
        if result.response:
            print(f"Gemma: {result.response}", flush=True)
            if speak and self.speech_enabled:
                self.speaker.say(result.response)

    def _respond(self, text: str, token: int) -> None:
        result = self._result("speak", text, None, time.monotonic())
        self._publish_result(result, token)
