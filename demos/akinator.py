"""Real-Life Akinator demo using the shared bounded agent loop."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from agent.loop import AgentLoop, AgentLoopError
from agent.prompts import AGENT_CORE, AKINATOR_PROMPT
from audio.mic import record_until_silence
from audio.stt import transcribe
from audio.tts import speak
from tools.registry import AKINATOR_ACTION_SCHEMAS, tool_name


def normalize_yes_no(text: str) -> str:
    words = set(re.findall(r"[a-z]+", text.lower()))
    if words & {"yes", "yeah", "yep", "correct", "right", "sure"}:
        return "yes"
    if words & {"no", "nope", "wrong", "incorrect"}:
        return "no"
    return "not sure"


@dataclass(frozen=True)
class GameResult:
    won: bool
    target: str
    guess: str
    questions: int
    gemma_look: str
    duration_seconds: float
    log_path: str


class AkinatorGame:
    def __init__(
        self,
        *,
        text_mode: bool,
        scripted_target: str | None = None,
        speech: bool = True,
        log_dir: str | Path | None = None,
    ) -> None:
        self.text_mode = text_mode
        self.scripted_target = scripted_target
        self.speech = speech
        self.loop = AgentLoop(log_dir=log_dir)

    def _say(self, text: str) -> None:
        clean = " ".join(text.split())
        print(f"Gemma: {clean}", flush=True)
        self.loop.log("SAY", text=clean)
        if self.speech:
            speak(clean)

    def _scripted_answer(self, question: str) -> str:
        assert self.scripted_target
        if self.scripted_target.lower() in question.lower():
            answer = "yes"
            self.loop.log(
                "SCRIPTED_USER",
                target=self.scripted_target,
                question=question,
                answer=answer,
                method="direct-target-match",
            )
            return answer
        answer, _ = self.loop._step(
            [
                {
                    "role": "system",
                    "content": "You simulate a truthful Akinator player. Reply with exactly yes, no, or not sure.",
                },
                {
                    "role": "user",
                    "content": f"Secret object: {self.scripted_target}\nQuestion: {question}",
                },
            ]
        )
        normalized = normalize_yes_no(answer)
        self.loop.log("SCRIPTED_USER", target=self.scripted_target, question=question, answer=normalized)
        return normalized

    def _answer(self, question: str) -> str:
        if self.scripted_target:
            answer = self._scripted_answer(question)
            print(f"User: {answer}", flush=True)
            return answer
        if self.text_mode:
            return normalize_yes_no(input("You [yes/no/not sure]: "))
        print("Speak your answer now.", flush=True)
        return normalize_yes_no(transcribe(record_until_silence()))

    @staticmethod
    def _argument(call: dict, key: str) -> str:
        arguments = (call.get("function") or {}).get("arguments") or {}
        return " ".join(str(arguments.get(key) or "").split())

    def run(self) -> GameResult:
        started = time.monotonic()
        self.loop.log("GAME_START", mode="akinator", text_mode=self.text_mode)
        inventory = self.loop.room_scan()

        # Gemma decides which already-scanned side merits a re-check. This is the
        # visible autonomous move required by the demo, not a fixed controller move.
        gemma_look = self.loop.choose_horizontal_look()
        recheck_path, _ = self.loop.execute_look(gemma_look)
        recheck_summary = self.loop.inventory_frame(gemma_look.removeprefix("look_"), recheck_path)
        inventory = f"{inventory}\n- autonomous re-check: {recheck_summary}"

        messages: list[dict] = [
            {"role": "system", "content": f"{AGENT_CORE}\n\n{AKINATOR_PROMPT}"},
            {
                "role": "user",
                "content": f"""Room inventory from your camera sweep:
{inventory}

The user says: I'm thinking of something in this room. Guess what it is.
Call ask_user for one yes/no question at a time. Ask at least one question before guessing.
Call final_answer only for a concrete evidence-based guess. Do not output an action as plain text.""",
            },
        ]
        guess = ""

        for _ in range(self.loop.max_questions + 3):
            model_text, calls = self.loop._step(messages, tools=AKINATOR_ACTION_SCHEMAS)
            if not calls:
                if "?" in model_text:
                    calls = [
                        {
                            "function": {
                                "name": "ask_user",
                                "arguments": {"question": model_text},
                            }
                        }
                    ]
                    self.loop.log("PARSED_TEXT_ACTION", tool="ask_user", text=model_text)
                elif re.search(r"\b(?:i guess|my guess|your object is)\b", model_text, re.IGNORECASE):
                    calls = [
                        {
                            "function": {
                                "name": "final_answer",
                                "arguments": {"text": model_text},
                            }
                        }
                    ]
                    self.loop.log("PARSED_TEXT_ACTION", tool="final_answer", text=model_text)
            if not calls:
                messages.append(
                    {"role": "user", "content": "Use exactly one supplied tool now: ask_user or final_answer."}
                )
                continue
            call = calls[0]
            name = tool_name(call)
            if name == "ask_user":
                question = self._argument(call, "question")
                if not question:
                    raise AgentLoopError("Gemma emitted ask_user without a question")
                if self.loop.memory.questions >= self.loop.max_questions:
                    messages.append({"role": "user", "content": "Question limit reached. Make your best final answer."})
                    continue
                self.loop.memory.questions += 1
                self._say(question)
                answer = self._answer(question)
                self.loop.log("ASK", question=question, answer=answer)
                messages.extend(
                    [
                        {"role": "assistant", "content": f"I asked: {question}"},
                        {"role": "user", "content": answer},
                    ]
                )
                continue
            if name == "final_answer":
                guess = self._argument(call, "text")
                if self.loop.memory.questions < 1:
                    messages.append({"role": "user", "content": "Ask at least one yes/no question before guessing."})
                    continue
                if not guess:
                    raise AgentLoopError("Gemma emitted final_answer without guess text")
                if not guess.lower().startswith("i guess"):
                    guess = f"I guess your object is the {guess.rstrip('.')} .".replace(" .", ".")
                self._say(guess)
                if self.scripted_target:
                    confirmation = "yes" if self.scripted_target.lower() in guess.lower() else "no"
                    print(f"User: {confirmation}", flush=True)
                else:
                    confirmation = self._answer("Is that correct?")
                self.loop.log("GUESS", text=guess, confirmation=confirmation)
                if confirmation == "yes":
                    duration = time.monotonic() - started
                    self.loop.log("GAME_RESULT", result="PASS", duration_seconds=round(duration, 3))
                    return GameResult(
                        True,
                        self.scripted_target or "human-selected",
                        guess,
                        self.loop.memory.questions,
                        gemma_look,
                        duration,
                        str(self.loop.log_path),
                    )
                messages.extend(
                    [
                        {"role": "assistant", "content": guess},
                        {"role": "user", "content": "No. Continue eliminating candidates."},
                    ]
                )
                continue
            raise AgentLoopError(f"Gemma emitted unsupported Akinator tool: {name}")

        raise AgentLoopError("Akinator did not win within the bounded game")


def run_games(
    count: int,
    *,
    text_mode: bool,
    scripted_target: str | None,
    speech: bool,
    log_dir: str | Path | None = None,
) -> list[GameResult]:
    if count < 1:
        raise ValueError("count must be positive")
    results = []
    for _ in range(count):
        results.append(
            AkinatorGame(
                text_mode=text_mode,
                scripted_target=scripted_target,
                speech=speech,
                log_dir=log_dir,
            ).run()
        )
    return results
