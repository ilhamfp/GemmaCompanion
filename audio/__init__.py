"""Offline microphone, speech recognition, and speech synthesis APIs."""

from .mic import record_until_silence
from .speaker import play_audio
from .stt import transcribe
from .tts import prerender, speak, speak_cached, wait_until_silent

__all__ = [
    "play_audio",
    "prerender",
    "record_until_silence",
    "speak",
    "speak_cached",
    "transcribe",
    "wait_until_silent",
]
