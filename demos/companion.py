"""Persistent, physically interruptible voice-and-vision companion session."""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from agent.gemma import GemmaClient
from audio.continuous import ContinuousMicrophone, VoiceSegment, temporary_segment_wav
from audio.fast_stt import transcribe_fast
from audio.interruptible import InterruptibleSpeech
from audio.volume import VOLUME_STEP, adjust_volume, set_volume
from camera.capture import CameraCaptureError, capture_image
from camera.obsbot import look_center, look_down, look_left, look_right, look_up
from demos.elderly import ElderlyFinder, FinderCancelled, found_target_sentence
from tools.registry import (
    COMPANION_DECISION_SCHEMAS,
    MOVEMENT_COMPLETION_SCHEMAS,
    tool_name,
)

MIN_AVAILABLE_BYTES = 500 * 1024 * 1024
READY_CUE = "Hi, I'm Gemma!"
VISION_PROMPT = """Describe only what is clearly visible in this fresh camera image.
Use one or two short spoken sentences. Name the main concrete objects and their useful physical locations.
Do not mention pixels, the image, or anything outside the view. Do not invent uncertain details."""
CONVERSATION_PROMPT = """You are Gemma Companion, an offline embodied assistant on a Jetson.
Reply in one or two short spoken sentences with normal punctuation and no markdown.
Never claim to see something unless it came from a fresh camera observation in this conversation.
Use the supplied tools whenever the request needs a physical action, a device setting, a systematic
search, or current visual evidence. Select tools from meaning and context, not memorized wording.
Never merely promise or narrate an available action and never ask for details an appropriate tool does
not require: call the tool instead. Infer tool arguments that are clear from ordinary language, including
relative directions and quantities, rather than asking the user to repeat them.
When one request asks you both to turn and to observe or report from there, call the appropriate
movement function followed by inspect_view in the same action-selection response.
For find_object, preserve the requested identity and add only stable visual traits you actually know.
Your audible voice comes from the physical USB speaker, so requests about how loud or soft you sound
are device-setting requests, not changes to writing style.
Never claim that an action happened until its tool succeeds. If no tool is needed, answer normally."""
AGENT_DECISION_PROMPT = f"""{CONVERSATION_PROMPT}
For this action-selection turn, call one or more supplied functions and produce no prose.
Call respond_normally only when the request is fully answerable without a physical action, current
camera evidence, an object search, or a device setting. The live camera is already available, so never
ask for an image or ask the user to show a present or referenced thing. Treat anything they say they
are currently presenting, holding, showing, pointing at, or asking about in their surroundings as
already available to inspect_view. Tool arguments must be inferred from ordinary language.
General-knowledge, factual, and hypothetical questions with no
reference to the user's current surroundings must call respond_normally, even when their subject could
theoretically be photographed."""
MOVEMENT_COMPLETION_PROMPT = """You are the completion checker after a physical camera movement succeeded.
Call inspect_view only when fulfilling the original request still requires fresh visual evidence from the new pose.
Call finish_movement when the original request asked only to reposition or aim, with no camera-derived answer.
Classify the whole meaning, including any clause after the movement. Seeing, describing, reporting a scene,
reading text, identifying, comparing, checking, and answering about the destination require inspect_view.
Merely naming a visible destination does not.
Examples:
- Original request: Point toward the doorway. -> finish_movement
- Original request: Point toward the doorway and tell me whether it is open. -> inspect_view
- Original request: Face the desk. -> finish_movement
- Original request: Face the desk, then summarize what is on it. -> inspect_view
Call exactly one supplied function and produce no prose."""
TOOL_REPAIR_PROMPT = """The previous assistant text did not execute anything. Map the original request
to the function that can actually fulfill it.
A request about a concrete thing in the user's present environment cannot be answered from language
knowledge. If the user refers to a current thing deictically or says they hold, show, present, point at,
read, see, or ask what it is, inspect_view is mandatory. The live camera supplies the image automatically;
asking the user to provide or clarify it is forbidden.
For example, a general question about how barcode scanners work uses respond_normally, while a question
asking what this device is uses inspect_view. General facts about colors use respond_normally, while the
color of the item the user is holding uses inspect_view.
If the prior text narrated a physical action, call that action. Use respond_normally only for
language-knowledge requests with no current physical referent. Call exactly one function and no prose."""
REQUEST_REQUIREMENT_PROMPT = """Classify what the user's request requires. Output exactly ACTION,
CAMERA, or KNOWLEDGE.
ACTION means a device action or systematic search is required: moving or aiming the camera, finding an
object, changing speaker volume, stopping speech, or sleeping. When both movement and seeing are
requested, choose ACTION.
CAMERA means no other action is requested but a correct answer requires fresh pixels from the live
environment: a current object, scene, appearance, writing, screen, label, message, or communication
being shown, held, presented, pointed at, nearby, or referenced by this, that, these, or those.
KNOWLEDGE means the request can be answered from language knowledge or conversation without a device
action or fresh physical evidence.
Examples:
- Turn left and describe the scene. -> ACTION
- Find my glasses. -> ACTION
- Is this message a scam? -> CAMERA
- What warning signs are common in fraudulent emails? -> KNOWLEDGE
- Which color is this item in my hand? -> CAMERA
- Why do leaves look green? -> KNOWLEDGE"""
VISUAL_QUESTION_PROMPT = """Answer the user's question using only this fresh camera view.
If a phone or message is shown, read only text that is genuinely legible.
For a suspected scam, explain the concrete warning signs, avoid claiming certainty when text is unclear,
and recommend not clicking links or sharing codes and verifying the sender through an independent trusted channel.
Reply in two or three short spoken sentences with no markdown."""
VISUAL_TARGET_MODIFIERS = {
    "black",
    "blue",
    "bright",
    "dark",
    "green",
    "large",
    "light",
    "oval",
    "rectangular",
    "red",
    "round",
    "rounded",
    "small",
    "white",
    "wireless",
    "yellow",
}


def available_memory_bytes() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise RuntimeError("MemAvailable is unavailable")


def preserves_target_identity(original: str, candidate: str) -> bool:
    """Reject visual rewrites that discard the named product or object type."""

    identity_tokens = {
        word
        for word in re.findall(r"[a-z0-9]+", original.casefold())
        if len(word) >= 3 and word not in VISUAL_TARGET_MODIFIERS
    }
    candidate_tokens = set(re.findall(r"[a-z0-9]+", candidate.casefold()))
    return bool(candidate) and len(candidate) <= 160 and identity_tokens <= candidate_tokens


@dataclass(frozen=True)
class CompanionResult:
    action: str
    response: str
    direction: str
    image_path: str | None
    latency_seconds: float

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
        speech_mode: str | None = None,
    ) -> None:
        self.speech_enabled = speech
        self.microphone_enabled = microphone
        self.gemma = gemma or GemmaClient()
        self.speaker = speaker or InterruptibleSpeech()
        self.mic = mic or ContinuousMicrophone(on_speech_start=self._on_speech_start)
        self.speech_mode = (speech_mode or os.environ.get("GEMMA_SPEECH_MODE", "whisper")).strip().casefold()
        if self.speech_mode not in {"direct", "whisper"}:
            raise ValueError("GEMMA_SPEECH_MODE must be 'direct' or 'whisper'")
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

    def _capture_fresh(self, output_dir: Path) -> str:
        """Retry a transient malformed or unavailable camera frame."""

        for attempt in range(1, 4):
            try:
                return capture_image(output_dir)
            except CameraCaptureError as exc:
                self._log("CAPTURE_RETRY", attempt=attempt, error=str(exc))
                if attempt == 3:
                    raise
                time.sleep(0.25)
        raise RuntimeError("camera retry loop exited unexpectedly")

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
            self._spawn(self._warm_agent_decision, token)
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
        health_interval = float(os.environ.get("GEMMA_HEALTH_INTERVAL_SECONDS", "5"))
        next_health_check = time.monotonic() + health_interval
        try:
            while not self._stop.wait(0.5):
                if self.microphone_enabled and self.mic.last_error is not None:
                    raise RuntimeError(f"continuous microphone failed: {self.mic.last_error}")
                if time.monotonic() >= next_health_check:
                    self.gemma.health()
                    next_health_check = time.monotonic() + health_interval
        finally:
            self.stop()

    def submit_text(self, text: str) -> int:
        """Inject a turn for deterministic verification while preserving latest-turn semantics."""

        token = self._new_turn()
        self.speaker.interrupt()
        self._spawn(self.handle_text, text, token)
        return token

    def handle_text(self, text: str, token: int | None = None) -> CompanionResult:
        """Let Gemma interpret and execute one text turn through the shared tool registry."""

        started = time.monotonic()
        active_token = self._new_turn() if token is None else token
        clean = " ".join(text.split())
        if not clean:
            raise ValueError("transcript must not be empty")
        print(f"You: {clean}", flush=True)
        self._log("TRANSCRIPT", turn=active_token, text=clean, routing="gemma_tools")
        return self._agent_turn(clean, None, active_token, started)

    def handle_audio(
        self,
        wav_path: str,
        token: int | None = None,
        *,
        started: float | None = None,
    ) -> CompanionResult:
        """Let Gemma understand a WAV and select tools in the same native multimodal call."""

        active_token = self._new_turn() if token is None else token
        turn_started = time.monotonic() if started is None else started
        self._log("DIRECT_AUDIO_REQUEST", turn=active_token, routing="gemma_audio_tools")
        print("You: [direct audio]", flush=True)
        return self._agent_turn(None, wav_path, active_token, turn_started)

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
            if self.speech_mode == "direct":
                self._spawn(self._handle_direct_segment, segment, token)
            else:
                self._transcribe_segment(segment, token)

    def _handle_direct_segment(self, segment: VoiceSegment, token: int) -> None:
        self.last_segment_ended_at = segment.ended_at
        self._log(
            "DIRECT_AUDIO_SEGMENT",
            turn=token,
            utterance_seconds=round(segment.duration_seconds, 3),
            peak_rms=round(segment.peak_rms, 1),
        )
        with temporary_segment_wav(segment) as path:
            if self._is_current(token):
                self.handle_audio(path, token, started=segment.ended_at)
            else:
                self._log("STALE_AUDIO_DISCARDED", turn=token)

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
                image_path = self._capture_fresh(Path.cwd() / "captures" / "companion")
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

    def _warm_agent_decision(self, token: int) -> None:
        """Prime the second llama.cpp slot with the stable action-selection prefix."""

        try:
            warm_client = GemmaClient(model=self.gemma.model, endpoint=self.gemma.endpoint)
            warm_client.step(
                [
                    {"role": "system", "content": AGENT_DECISION_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            "Physical state: awake; camera direction: center.\n"
                            "User request: Briefly acknowledge that you are ready."
                        ),
                    },
                ],
                tools=COMPANION_DECISION_SCHEMAS,
                max_tokens=1,
                tool_choice="required",
            )
            self._log(
                "AGENT_PREFIX_WARMUP",
                turn=token,
                model_latency_seconds=round(warm_client.last_latency_seconds, 3),
            )
        except Exception as exc:
            self._log("AGENT_PREFIX_WARMUP_SKIPPED", turn=token, error=str(exc))

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
            image_path = self._capture_fresh(Path.cwd() / "captures" / "companion")
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

    def _answer_visual(
        self,
        question: str | None,
        token: int,
        started: float,
        *,
        audio_path: str | None = None,
        action: str = "visual_question",
    ) -> CompanionResult:
        if available_memory_bytes() < MIN_AVAILABLE_BYTES:
            result = self._result(
                "visual_question_refused_low_memory",
                "I don't have enough free memory to inspect safely.",
                None,
                started,
            )
            self._publish_result(result, token)
            return result
        with self._camera_lock:
            direction = self._direction
            image_path = self._capture_fresh(Path.cwd() / "captures" / "companion")
        request = (
            f"User's question: {question}"
            if question is not None
            else "The attached audio contains the user's original request."
        )
        text, _ = self.gemma.step(
            [
                {"role": "system", "content": CONVERSATION_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Current physical camera direction: {direction}.\n"
                        f"{request}\n{VISUAL_QUESTION_PROMPT}"
                    ),
                },
            ],
            [image_path],
            audios=[audio_path] if audio_path else None,
            max_tokens=56,
        )
        result = self._result(action, text, image_path, started)
        self._remember_turn(question, text, token)
        self._publish_result(result, token)
        return result

    def _finder_say(self, text: str, token: int) -> None:
        if not self._is_current(token):
            raise FinderCancelled("a newer user turn cancelled finder speech")
        if self.speech_enabled:
            self.speaker.say(text, words_per_minute=120)
            self.speaker.wait(timeout=60)
        if not self._is_current(token):
            raise FinderCancelled("a newer user turn cancelled finder speech")

    def _movement_needs_inspection(
        self,
        request: str | None,
        audio_path: str | None,
        direction: str,
        token: int,
    ) -> bool:
        user_content = (
            f"Original request: {request}\nCompleted direction: {direction}"
            if request is not None
            else f"The attached audio is the original request.\nCompleted direction: {direction}"
        )
        response, calls = self.gemma.step(
            [
                {"role": "system", "content": MOVEMENT_COMPLETION_PROMPT},
                {"role": "user", "content": user_content},
            ],
            tools=MOVEMENT_COMPLETION_SCHEMAS,
            audios=[audio_path] if audio_path else None,
            max_tokens=16,
            tool_choice="required",
        )
        selected = [tool_name(call) for call in calls]
        self._log(
            "MOVEMENT_COMPLETION_DECISION",
            turn=token,
            direction=direction,
            tools=selected,
            model_latency_seconds=round(self.gemma.last_latency_seconds, 3),
            text=" ".join(response.split()),
        )
        return "inspect_view" in selected

    def _request_requirement(
        self,
        request: str | None,
        audio_path: str | None,
        token: int,
    ) -> str:
        user_content = (
            request
            if request is not None
            else "Classify the request in the attached audio."
        )
        response, _ = self.gemma.step(
            [
                {"role": "system", "content": REQUEST_REQUIREMENT_PROMPT},
                {"role": "user", "content": user_content},
            ],
            audios=[audio_path] if audio_path else None,
            max_tokens=4,
        )
        classification = response.strip().split(maxsplit=1)[0].strip("`.,:").casefold()
        if classification not in {"action", "camera", "knowledge"}:
            classification = "action"
        self._log(
            "REQUEST_REQUIREMENT_DECISION",
            turn=token,
            classification=classification,
            model_latency_seconds=round(self.gemma.last_latency_seconds, 3),
        )
        return classification

    @staticmethod
    def _repair_messages(text: str | None, response: str) -> list[dict]:
        return [
            {"role": "system", "content": AGENT_DECISION_PROMPT},
            {
                "role": "user",
                "content": (
                    text
                    if text is not None
                    else "Treat the attached audio as the user's original request."
                ),
            },
            {"role": "assistant", "content": response},
            {"role": "user", "content": TOOL_REPAIR_PROMPT},
        ]

    def _find_object(
        self,
        request: str,
        target: str,
        token: int,
        started: float,
    ) -> CompanionResult:
        self._log(
            "FINDER_HANDOFF",
            turn=token,
            request=request,
            target=target,
            target_source="gemma_tool_argument",
        )
        finder = ElderlyFinder(
            speech=False,
            log_dir=self.log_path.parent,
            gemma=self.gemma,
            say_callback=lambda text: self._finder_say(text, token),
            continue_check=lambda: self._is_current(token),
            camera_lock=self._camera_lock,
        )
        try:
            found = finder.search_live(request, target=target)
        except FinderCancelled:
            with self._camera_lock:
                look_center()
                self._direction = "center"
            result = self._result("find_cancelled", "", None, started)
            self._publish_result(result, token, speak=False)
            return result

        with self._camera_lock:
            if found.found:
                self._direction = found.direction or self._direction
            else:
                look_center()
                self._direction = "center"
        response = found_target_sentence(target, found.location) if found.found else found.location
        result = self._result(
            "find_found" if found.found else "find_not_found",
            response,
            None,
            started,
        )
        self._log(
            "FINDER_HANDOFF_RESULT",
            turn=token,
            found=found.found,
            finder_log=found.log_path,
            gemma_moves=found.gemma_moves,
            location=found.location,
        )
        self._remember_turn(request, response, token)
        # The finder already printed and spoke its terminal result through
        # _finder_say; retain the result without duplicating console output.
        self._publish_result(result, token, speak=False, display=False)
        return result

    def _agent_turn(
        self,
        text: str | None,
        audio_path: str | None,
        token: int,
        started: float,
    ) -> CompanionResult:
        if available_memory_bytes() < MIN_AVAILABLE_BYTES:
            result = self._result(
                "agent_refused_low_memory",
                "I don't have enough free memory to answer safely.",
                None,
                started,
            )
            self._publish_result(result, token)
            return result
        if self._asleep:
            self._asleep = False
            self._log("WAKE_ON_SPEECH", turn=token)
        state = f"Physical state: awake; camera direction: {self.direction}."
        user_request = (
            f"{state}\nUser request: {text}"
            if text is not None
            else f"{state}\nTreat the attached audio as the user's request."
        )
        messages: list[dict] = [
            {"role": "system", "content": AGENT_DECISION_PROMPT},
            {
                "role": "user",
                "content": user_request,
            },
        ]
        moved: list[str] = []
        for round_index in range(1, 3):
            response, calls = self.gemma.step(
                messages,
                tools=COMPANION_DECISION_SCHEMAS,
                audios=[audio_path] if audio_path else None,
                max_tokens=64 if round_index == 1 else 24,
                tool_choice="required",
            )
            response_completed = self.gemma.last_finish_reason == "stop"
            if not self._is_current(token):
                result = self._result("stale_cancelled", "", None, started)
                self._publish_result(result, token, speak=False)
                return result
            calls = calls[:6]
            selected = [tool_name(call) for call in calls]
            self._log(
                "AGENT_DECISION",
                turn=token,
                round=round_index,
                input_mode="audio" if audio_path else "text",
                tools=selected,
                model_latency_seconds=round(self.gemma.last_latency_seconds, 3),
                text=" ".join(response.split()),
            )
            if not calls:
                if round_index == 1:
                    requirement = self._request_requirement(text, audio_path, token)
                    if not self._is_current(token):
                        result = self._result("stale_cancelled", "", None, started)
                        self._publish_result(result, token, speak=False)
                        return result
                    if requirement == "camera":
                        return self._answer_visual(
                            text,
                            token,
                            started,
                            audio_path=audio_path,
                        )
                    if requirement == "knowledge" and response and response_completed:
                        self._remember_turn(text, response, token)
                        result = self._result("chat", response, None, started)
                        self._log(
                            "DIRECT_KNOWLEDGE_RESPONSE",
                            turn=token,
                            saved_regeneration=True,
                        )
                        self._publish_result(result, token)
                        return result
                    messages = self._repair_messages(text, response)
                    continue
                break

            assistant_message: dict = {"role": "assistant", "content": response}
            normalized_calls: list[dict] = []
            for index, original_call in enumerate(calls, start=1):
                call = dict(original_call)
                call.setdefault("id", f"companion-{token}-{round_index}-{index}")
                call.setdefault("type", "function")
                normalized_calls.append(call)
            assistant_message["tool_calls"] = normalized_calls
            messages.append(assistant_message)

            inspect_requested = False
            made_progress = False
            retry_requested = False
            for call in normalized_calls:
                selected_tool = tool_name(call)
                arguments = (call.get("function") or {}).get("arguments") or {}
                if not isinstance(arguments, dict):
                    arguments = {}
                self._log(
                    "AGENT_TOOL_CALL",
                    turn=token,
                    round=round_index,
                    tool=selected_tool,
                    arguments=arguments,
                )
                if selected_tool.startswith("look_"):
                    direction = selected_tool.removeprefix("look_")
                    if direction in {"left", "right", "up", "down", "center"}:
                        self._move(direction, token)
                        moved.append(direction)
                        made_progress = True
                    continue
                if selected_tool == "inspect_view":
                    inspect_requested = True
                    made_progress = True
                    continue
                if selected_tool == "find_object":
                    target = " ".join(str(arguments.get("target") or "").split())
                    if target:
                        request = text or f"Find {target}"
                        return self._find_object(request, target, token, started)
                    continue
                if selected_tool == "respond_normally":
                    requirement = self._request_requirement(text, audio_path, token)
                    if not self._is_current(token):
                        result = self._result("stale_cancelled", "", None, started)
                        self._publish_result(result, token, speak=False)
                        return result
                    if requirement == "camera":
                        return self._answer_visual(
                            text,
                            token,
                            started,
                            audio_path=audio_path,
                        )
                    if requirement == "action":
                        if round_index == 1:
                            messages = self._repair_messages(text, response)
                            made_progress = False
                            retry_requested = True
                            break
                        continue
                    final_text, _ = self.gemma.step(
                        [
                            {"role": "system", "content": CONVERSATION_PROMPT},
                            *self._conversation[-6:],
                            {
                                "role": "user",
                                "content": (
                                    text
                                    if text is not None
                                    else "Answer the request in the attached audio."
                                ),
                            },
                        ],
                        audios=[audio_path] if audio_path else None,
                        max_tokens=64,
                    )
                    if not self._is_current(token):
                        result = self._result("stale_cancelled", "", None, started)
                        self._publish_result(result, token, speak=False)
                        return result
                    self._remember_turn(text, final_text, token)
                    result = self._result("chat", final_text, None, started)
                    self._publish_result(result, token)
                    return result
                if selected_tool == "cancel_current_response":
                    self.speaker.interrupt()
                    result = self._result("stop", "Stopped.", None, started)
                    self._remember_turn(text, result.response, token)
                    self._publish_result(result, token, speak=False)
                    return result
                if selected_tool == "sleep":
                    self._asleep = True
                    result = self._result(
                        "sleep",
                        "Going idle. The next time you speak, I'll wake up.",
                        None,
                        started,
                    )
                    self._remember_turn(text, result.response, token)
                    self._publish_result(result, token)
                    return result
                if selected_tool in {"make_voice_louder", "make_voice_softer", "set_volume"}:
                    if selected_tool == "set_volume":
                        try:
                            requested = int(arguments.get("percent"))
                        except (TypeError, ValueError):
                            requested = -1
                        if not 0 <= requested <= 100:
                            result = self._result(
                                "volume_invalid",
                                "Please choose a volume from zero to one hundred percent.",
                                None,
                                started,
                            )
                            self._publish_result(result, token)
                            return result
                        volume = set_volume(requested)
                        action = "volume_set"
                    else:
                        direction = "up" if selected_tool == "make_voice_louder" else "down"
                        delta = VOLUME_STEP if direction == "up" else -VOLUME_STEP
                        volume = adjust_volume(delta)
                        action = f"volume_{direction}"
                    result = self._result(action, f"Volume {volume} percent.", None, started)
                    self._remember_turn(text, result.response, token)
                    self._publish_result(result, token)
                    return result

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": json.dumps({"ok": False, "error": "unsupported tool"}),
                    }
                )

            if retry_requested:
                continue
            if inspect_requested:
                action = f"look_{moved[-1]}_and_inspect" if moved else "visual_question"
                return self._answer_visual(
                    text,
                    token,
                    started,
                    audio_path=audio_path,
                    action=action,
                )
            if made_progress:
                needs_inspection = bool(moved) and self._movement_needs_inspection(
                    text, audio_path, moved[-1], token
                )
                if not self._is_current(token):
                    result = self._result("stale_cancelled", "", None, started)
                    self._publish_result(result, token, speak=False)
                    return result
                if needs_inspection:
                    return self._answer_visual(
                        text,
                        token,
                        started,
                        audio_path=audio_path,
                        action=f"look_{moved[-1]}_and_inspect",
                    )
                response = f"Looking {moved[-1]}." if moved else "Done."
                action = f"look_{moved[-1]}" if moved else "agent_action"
                self._remember_turn(text, response, token)
                result = self._result(action, response, None, started)
                self._publish_result(result, token)
                return result
            break

        response = f"Looking {moved[-1]}." if moved else "I couldn't safely execute that request."
        action = f"look_{moved[-1]}" if moved else "agent_limit"
        self._remember_turn(text, response, token)
        result = self._result(action, response, None, started)
        self._publish_result(result, token)
        return result

    def _remember_turn(self, user_text: str | None, response: str, token: int) -> None:
        if not response or not self._is_current(token):
            return
        if user_text is not None:
            self._conversation.append({"role": "user", "content": user_text})
        self._conversation.append({"role": "assistant", "content": response})
        self._conversation[:] = self._conversation[-8:]

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

    def _publish_result(
        self,
        result: CompanionResult,
        token: int,
        *,
        speak: bool = True,
        display: bool = True,
    ) -> None:
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
        if result.response and display:
            print(f"Gemma: {result.response}", flush=True)
            if speak and self.speech_enabled:
                self.speaker.say(result.response)

    def _respond(self, text: str, token: int) -> None:
        result = self._result("speak", text, None, time.monotonic())
        self._publish_result(result, token)
