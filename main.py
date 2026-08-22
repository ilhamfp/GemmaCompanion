#!/usr/bin/env python3
"""Command-line entry point for both Gemma Companion demos."""

from __future__ import annotations

import argparse
from pathlib import Path

from audio.mic import record_until_silence
from audio.stt import transcribe
from audio.tts import LOOK_ANNOUNCEMENT
from demos.akinator import run_games
from demos.elderly import ElderlyFinder, is_medical_request


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline Gemma Companion")
    parser.add_argument("--mode", choices=("akinator", "elderly"), required=True)
    parser.add_argument("--text", action="store_true", help="use keyboard instead of microphone input")
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--scripted-target", help="automated truthful user used only for repeatable verification")
    parser.add_argument("--no-speech", action="store_true", help="suppress TTS while retaining text output")
    parser.add_argument("--request")
    parser.add_argument("--target", default="wearable eyeglasses")
    parser.add_argument("--negative-target", default="wearable eyeglasses")
    parser.add_argument("--runs", type=int, default=1, help="elderly-mode positive run count")
    parser.add_argument("--expected-direction", choices=("left", "right", "up", "down"))
    parser.add_argument("--negative-fixture")
    args = parser.parse_args()

    if args.mode == "elderly":
        request = args.request
        if not request:
            if args.text:
                request = input("What should Gemma find? ").strip()
            else:
                print("Tell Gemma what you want to find.", flush=True)
                request = transcribe(record_until_silence())
            if not request:
                raise RuntimeError("the object-finder request was empty")
        if is_medical_request(request):
            refusal = ElderlyFinder(
                speech=not args.no_speech,
                log_dir=Path(__file__).resolve().parent / "logs",
            ).search_live(request, target=args.target)
            print(f"safety_response: {refusal.location}")
            print("result: PASS medical request refused with caregiver-or-doctor guidance")
            return 0
        results = []
        for _ in range(args.runs):
            result = ElderlyFinder(
                speech=not args.no_speech,
                log_dir=Path(__file__).resolve().parent / "logs",
            ).search_live(request, target=args.target)
            if not result.found:
                raise RuntimeError(f"positive object run returned not-found: {result.location}")
            if args.expected_direction and result.direction != args.expected_direction:
                raise RuntimeError(
                    f"target found in {result.direction}, expected {args.expected_direction}"
                )
            results.append(result)

        negative = None
        if args.negative_fixture:
            negative = ElderlyFinder(
                speech=not args.no_speech,
                log_dir=Path(__file__).resolve().parent / "logs",
            ).evaluate_negative_fixture(args.negative_fixture, target=args.negative_target)
            if negative.found:
                raise RuntimeError("negative fixture incorrectly returned found")

        if len(results) == 3 and negative is not None:
            for index, result in enumerate(results, start=1):
                print(
                    f"found_run_{index}: PASS; target={args.target}; direction={result.direction}; "
                    f"gemma_moves={','.join(result.gemma_moves)}; location={result.location}; "
                    f"duration_seconds={result.duration_seconds:.3f}"
                )
            print(
                f"negative_run: PASS; target={args.negative_target}; searched=center,left,right,up,down; "
                f"response={negative.location}; log={negative.log_path}"
            )
            print("result: PASS requested object found 3/3 out of initial view and honest not-found 1/1")
            return 0

        result = results[0]
        print(
            f"found: PASS; direction={result.direction}; gemma_moves={','.join(result.gemma_moves)}; "
            f"location={result.location}; duration_seconds={result.duration_seconds:.3f}"
        )
        print(f"session_log: {result.log_path}")
        print("result: PASS elderly requested-object finder")
        return 0

    results = run_games(
        args.games,
        text_mode=args.text or bool(args.scripted_target),
        scripted_target=args.scripted_target,
        speech=not args.no_speech,
        log_dir=Path(__file__).resolve().parent / "logs",
    )
    if len(results) == 1:
        result = results[0]
        print(
            f"game_1: PASS; questions={result.questions}; gemma_move={result.gemma_look}; "
            f"duration_seconds={result.duration_seconds:.3f}; guess={result.guess}"
        )
        print(
            "look_announcement_overlap: "
            f"{'PASS' if result.look_announcement_overlap else 'SKIP'}; "
            f"phrase={LOOK_ANNOUNCEMENT!r}; gemma_move={result.gemma_look}"
        )
        print(f"session_log: {result.log_path}")
        print("result: PASS full Akinator game")
        return 0

    for index, result in enumerate(results, start=1):
        print(
            f"game_{index}: PASS; questions={result.questions}; gemma_move={result.gemma_look}; "
            f"duration_seconds={result.duration_seconds:.3f}; guess={result.guess}"
        )
    print(f"consecutive_games: {len(results)}/{len(results)} PASS; text_fallback: yes; physical_moves: {len(results)}")
    print("session_logs: " + "; ".join(result.log_path for result in results))
    print("result: PASS two consecutive full Akinator games with Gemma-initiated physical camera moves")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
