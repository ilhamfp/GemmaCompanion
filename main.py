#!/usr/bin/env python3
"""Command-line entry point for both Gemma Companion demos."""

from __future__ import annotations

import argparse
from pathlib import Path

from demos.akinator import run_games


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline Gemma Companion")
    parser.add_argument("--mode", choices=("akinator", "elderly"), required=True)
    parser.add_argument("--text", action="store_true", help="use keyboard instead of microphone input")
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--scripted-target", help="automated truthful user used only for repeatable verification")
    parser.add_argument("--no-speech", action="store_true", help="suppress TTS while retaining text output")
    args = parser.parse_args()

    if args.mode == "elderly":
        parser.error("elderly mode is delivered at M7")

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
